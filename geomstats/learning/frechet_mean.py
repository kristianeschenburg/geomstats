"""Frechet mean."""

import logging
import math

from sklearn.base import BaseEstimator

import geomstats.backend as gs
from geomstats.geometry.euclidean import EuclideanMetric
from geomstats.geometry.minkowski import MinkowskiMetric

EPSILON = 1e-4


def variance(points,
             base_point,
             metric,
             weights=None,
             point_type='vector'):
    """Variance of (weighted) points wrt a base point.

    Parameters
    ----------
    points : array-like, shape=[n_samples, dimension]

    weights : array-like, shape=[n_samples, 1], optional
    """
    n_points = gs.shape(points)[0]
    if weights is None:
        weights = gs.ones((n_points, 1))
    weights = gs.array(weights)

    sum_weights = gs.sum(weights)
    if point_type == 'vector':
        points = gs.to_ndarray(points, to_ndim=2)
        base_point = gs.to_ndarray(base_point, to_ndim=2)
        weights = gs.to_ndarray(weights, to_ndim=2, axis=1)
    if point_type == 'matrix':
        points = gs.to_ndarray(points, to_ndim=3)
        base_point = gs.to_ndarray(base_point, to_ndim=3)
        weights = gs.to_ndarray(weights, to_ndim=3, axis=1)
        weights = weights[:, :, 0]

    sq_dists = metric.squared_dist(base_point, points)
    var = gs.einsum('...k,...->...', weights, sq_dists)

    var = gs.sum(var)
    var /= sum_weights

    var = gs.to_ndarray(var, to_ndim=1)
    var = gs.to_ndarray(var, to_ndim=2, axis=1)
    return var


def linear_mean(points, weights=None):
    """Compute the weighted linear mean.

    The linear mean is the Frechet mean when points:
    - lie in a Euclidean space with Euclidean metric,
    - lie in a Minkowski space with Minkowski metric.

    Parameters
    ----------
    points : array-like, shape=[n_samples, dimension]
        Points to be averaged.

    weights : array-like, shape=[n_samples, 1], optional
        Weights associated to the points.

    Returns
    -------
    mean : array-like, shape=[1, dimension]
        Weighted linear mean of the points.
    """
    if isinstance(points, list):
        points = gs.vstack(points)
    points = gs.to_ndarray(points, to_ndim=2)
    n_points = gs.shape(points)[0]

    if isinstance(weights, list):
        weights = gs.vstack(weights)
    elif weights is None:
        weights = gs.ones((n_points, ))

    weighted_points = gs.einsum('...,...j->...j', weights, points)
    mean = (gs.sum(weighted_points, axis=0) / gs.sum(weights))
    mean = gs.to_ndarray(mean, to_ndim=2)
    return mean


def _default_gradient_descent(points, metric, weights,
                              max_iter, point_type, epsilon, verbose):
    if point_type == 'vector':
        points = gs.to_ndarray(points, to_ndim=2)
        einsum_str = 'nk,nj->j'
    if point_type == 'matrix':
        einsum_str = 'nkl,nij->ij'
        points = gs.to_ndarray(points, to_ndim=3)
    n_points = gs.shape(points)[0]

    if weights is None:
        weights = gs.ones((n_points, 1))
    weights = gs.array(weights)

    mean = points[0]
    if point_type == 'vector':
        weights = gs.to_ndarray(weights, to_ndim=2, axis=1)
        mean = gs.to_ndarray(mean, to_ndim=2)
    if point_type == 'matrix':
        weights = gs.to_ndarray(weights, to_ndim=3, axis=1)
        mean = gs.to_ndarray(mean, to_ndim=3)

    if n_points == 1:
        return mean

    sum_weights = gs.sum(weights)
    sq_dists_between_iterates = []
    iteration = 0
    sq_dist = gs.array([[0.]])
    var = gs.array([[0.]])

    while iteration < max_iter:
        condition = ~gs.logical_or(
            gs.isclose(var, 0.),
            gs.less_equal(sq_dist, epsilon * var))
        if not (condition[0, 0] or iteration == 0):
            break
        logs = metric.log(point=points, base_point=mean)

        tangent_mean = gs.einsum(einsum_str, weights, logs)
        tangent_mean /= sum_weights

        estimate_next = metric.exp(tangent_vec=tangent_mean, base_point=mean)

        sq_dist = metric.squared_dist(estimate_next, mean)
        sq_dists_between_iterates.append(sq_dist)

        var = variance(
            points=points,
            weights=weights,
            metric=metric,
            base_point=estimate_next,
            point_type=point_type)

        mean = estimate_next
        iteration += 1

    if iteration == max_iter:
        logging.warning(
            'Maximum number of iterations {} reached. '
            'The mean may be inaccurate'.format(max_iter))

    if verbose:
        logging.info('n_iter: {}, final variance: {}, final dist: {}'.format(
            iteration, var, sq_dist))

    mean = gs.to_ndarray(mean, to_ndim=2)
    return mean


def _ball_gradient_descent(points, metric, weights, max_iter,
                           lr=1e-3, tau=5e-3):
    if len(points) == 1:
        return points

    iteration = 0
    convergence = math.inf
    barycenter = points.mean(0, keepdims=True) * 0

    while convergence > tau and max_iter > iteration:

        iteration += 1

        grad_tangent = 2 * metric.log(points, barycenter)

        cc_barycenter = metric.exp(
            lr * grad_tangent.sum(0, keepdims=True), barycenter)

        convergence = metric.dist(cc_barycenter, barycenter).max().item()

        barycenter = cc_barycenter

    if iteration == max_iter:
        logging.warning(
            'Maximum number of iterations {} reached. The '
            'mean may be inaccurate'.format(max_iter))

    return barycenter


def _adaptive_gradient_descent(points,
                               metric,
                               weights=None,
                               max_iter=32,
                               epsilon=1e-12,
                               init_point=None,
                               point_type='vector'):
    """Compute the Frechet mean using gradient descent.

    Frechet mean of (weighted) points using adaptive time-steps
    The loss function optimized is :math:`||M_1(x)||_x`
    (where :math:`M_1(x)` is the tangent mean at x) rather than
    the mean-square-distance (MSD) because this simplifies computations.
    Adaptivity is done in a Levenberg-Marquardt style weighting variable tau
    between the first order and the second order Gauss-Newton gradient descent.

    Parameters
    ----------
    points : array-like, shape=[n_samples, dimension]
        Points to be averaged.

    weights : array-like, shape=[n_samples, 1], optional
        Weights associated to the points.

    max_iter : int, optional
        Maximum number of iterations for the gradient descent.

    init_point : array-like, shape=[n_init, dimension], optional
        Initial points.

    epsilon : float, optional
        Tolerance for stopping the gradient descent.

    Returns
    -------
    current_mean: array-like, shape=[n_samples, dimension]
        Weighted Frechet mean of the points.
    """
    tau_max = 1e6
    tau_mul_up = 1.6511111
    tau_min = 1e-6
    tau_mul_down = 0.1
    if point_type == 'matrix':
        raise NotImplementedError(
            'The Frechet mean with adaptive gradient descent is only'
            ' implemented for lists of vectors, and not matrices.')
    n_points = gs.shape(points)[0]

    if n_points == 1:
        return points

    if weights is None:
        weights = gs.ones((n_points, 1))

    weights = gs.array(weights)
    weights = gs.to_ndarray(weights, to_ndim=2, axis=1)

    sum_weights = gs.sum(weights)

    if init_point is None:
        current_mean = points[0]
    else:
        current_mean = init_point

    tau = 1.0
    iteration = 0

    logs = metric.log(point=points, base_point=current_mean)
    current_tangent_mean = gs.einsum('nk,nj->j', weights, logs)
    current_tangent_mean /= sum_weights
    sq_norm_current_tangent_mean = metric.squared_norm(current_tangent_mean,
                                                       base_point=current_mean)

    while (sq_norm_current_tangent_mean > epsilon ** 2
           and iteration < max_iter):
        iteration = iteration + 1
        shooting_vector = gs.to_ndarray(
            tau * current_tangent_mean,
            to_ndim=2)
        next_mean = metric.exp(
            tangent_vec=shooting_vector,
            base_point=current_mean)
        logs = metric.log(point=points, base_point=next_mean)
        next_tangent_mean = gs.einsum('nk,nj->j', weights, logs)
        next_tangent_mean /= sum_weights
        sq_norm_next_tangent_mean = metric.squared_norm(next_tangent_mean,
                                                        base_point=next_mean)
        if sq_norm_next_tangent_mean < sq_norm_current_tangent_mean:
            current_mean = next_mean
            current_tangent_mean = next_tangent_mean
            sq_norm_current_tangent_mean = sq_norm_next_tangent_mean
            tau = min(tau_max, tau_mul_up * tau)
        else:
            tau = max(tau_min, tau_mul_down * tau)

    if iteration == max_iter:
        logging.warning(
            'Maximum number of iterations {} reached. '
            'The mean may be inaccurate'.format(max_iter))

    return gs.to_ndarray(current_mean, to_ndim=2)


class FrechetMean(BaseEstimator):
    """Empirical Frechet mean.

    Parameters
    ----------
    max_iter:
    """

    def __init__(self, metric,
                 max_iter=32,
                 epsilon=EPSILON,
                 point_type='vector',
                 method='default',
                 verbose=False):
        self.metric = metric
        self.max_iter = max_iter
        self.epsilon = epsilon
        self.point_type = point_type
        self.method = method
        self.verbose = verbose

    def fit(self, X, y=None, weights=None):
        """Compute the empirical Frechet mean.

        Parameters
        ----------
        X : {array-like, sparse matrix}, shape (n_samples, n_features)
            The training input samples.
        y : array-like, shape (n_samples,) or (n_samples, n_outputs)
            The target values (class labels in classification, real numbers in
            regression).
            Ignored
        weights : array-like, shape=[n_samples, 1], optional

        Returns
        -------
        self : object
            Returns self.
        """
        # TODO(nina): Profile this code to study performance,
        # i.e. what to do with sq_dists_between_iterates.

        if isinstance(self.metric, (EuclideanMetric, MinkowskiMetric)):
            mean = linear_mean(points=X, weights=weights)

        elif self.method == 'default':
            mean = _default_gradient_descent(
                points=X, weights=weights, metric=self.metric,
                max_iter=self.max_iter,
                point_type=self.point_type, epsilon=self.epsilon,
                verbose=self.verbose)
        elif self.method == 'adaptive':
            mean = _adaptive_gradient_descent(
                points=X, weights=weights, metric=self.metric,
                max_iter=self.max_iter,
                epsilon=1e-12)
        elif self.method == 'frechet-poincare-ball':
            mean = _ball_gradient_descent(
                points=X, weights=weights, metric=self.metric,
                max_iter=self.max_iter)

        self.estimate_ = mean

        return self
