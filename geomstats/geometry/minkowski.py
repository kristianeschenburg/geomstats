"""Minkowski space."""

import geomstats.backend as gs
from geomstats.geometry.manifold import Manifold
from geomstats.geometry.riemannian_metric import RiemannianMetric


class Minkowski(Manifold):
    """Class for Minkowski Space."""

    def __init__(self, dimension):
        super(Minkowski, self).__init__(dimension=dimension)
        self.metric = MinkowskiMetric(dimension)

    def belongs(self, point):
        """Evaluate if a point belongs to the Minkowski space.

        Parameters
        ----------
        point : array-like, shape=[n_samples, dimension]
                Input points.

        Returns
        -------
        belongs : array-like, shape=[n_samples,]
        """
        point_dim = point.shape[-1]
        belongs = point_dim == self.dimension
        if gs.ndim(point) == 2:
            belongs = gs.tile([belongs], (point.shape[0],))

        return belongs

    def random_uniform(self, n_samples=1, bound=1.):
        """Sample in the Minkowski space with the uniform distribution.

        Parameters
        ----------
        n_samples: int, optional
        bound: float, optional

        Returns
        -------
        points : array-like, shape=[n_samples, dimension]
                 Sampled points.
        """
        size = (self.dimension,)
        if n_samples != 1:
            size = (n_samples, self.dimension)
        point = bound * gs.random.rand(*size) * 2 - 1

        return point


class MinkowskiMetric(RiemannianMetric):
    """Class for the pseudo-Riemannian Minkowski metric.

    The metric is flat: the inner product is independent of the base point.
    """

    def __init__(self, dimension):
        super(MinkowskiMetric, self).__init__(
            dimension=dimension,
            signature=(dimension - 1, 1, 0))

    def inner_product_matrix(self, base_point=None):
        """Compute the inner product matrix, independent of the base point.

        Parameters
        ----------
        base_point: array-like, shape=[n_samples, dimension]

        Returns
        -------
        inner_prod_mat: array-like, shape=[n_samples, dimension, dimension]
        """
        inner_prod_mat = gs.eye(self.dimension - 1, self.dimension - 1)
        first_row = gs.array([0.] * (self.dimension - 1))
        first_row = gs.to_ndarray(first_row, to_ndim=2, axis=1)
        inner_prod_mat = gs.vstack(
            [gs.transpose(first_row), inner_prod_mat])

        first_column = gs.array([-1.] + [0.] * (self.dimension - 1))
        first_column = gs.to_ndarray(first_column, to_ndim=2, axis=1)
        inner_prod_mat = gs.hstack([first_column, inner_prod_mat])

        return inner_prod_mat

    def exp(self, tangent_vec, base_point):
        """Compute the Riemannian exponential of `tangent_vec` at `base_point`.

        The Riemannian exponential is the addition in the Minkowski space.

        Parameters
        ----------
        tangent_vec: array-like, shape=[n_samples, dimension]
                                 or shape=[1, dimension]
        base_point: array-like, shape=[n_samples, dimension]
                                or shape=[1, dimension]

        Returns
        -------
        exp: array-like, shape=[n_samples, dimension]
                          or shape-[n_samples, dimension]
        """
        exp = base_point + tangent_vec
        return exp

    def log(self, point, base_point):
        """Compute the Riemannian logarithm of `point` at `base_point`.

        The Riemannian logarithm is the subtraction in the Minkowski space.

        Parameters
        ----------
        point: array-like, shape=[n_samples, dimension]
                           or shape=[1, dimension]
        base_point: array-like, shape=[n_samples, dimension]
                                or shape=[1, dimension]

        Returns
        -------
        log: array-like, shape=[n_samples, dimension]
                          or shape-[n_samples, dimension]
        """
        log = point - base_point
        return log
