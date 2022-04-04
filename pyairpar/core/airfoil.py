import numpy as np
from pyairpar.core.param import Param
from pyairpar.core.anchor_point import AnchorPoint
from pyairpar.core.free_point import FreePoint
from pyairpar.core.base_airfoil_params import BaseAirfoilParams
from pyairpar.symmetric.symmetric_base_airfoil_params import SymmetricBaseAirfoilParams
from matplotlib.axes import Axes
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import typing
from shapely.geometry import Polygon, LineString


class Airfoil:

    def __init__(self,
                 number_coordinates: int = 100,
                 base_airfoil_params: BaseAirfoilParams or SymmetricBaseAirfoilParams = BaseAirfoilParams(),
                 anchor_point_tuple: typing.Tuple[AnchorPoint, ...] = (),
                 free_point_tuple: typing.Tuple[FreePoint, ...] = (),
                 override_parameters: list = None
                 ):

        self.nt = number_coordinates
        self.params = []
        self.bounds = []
        self.base_airfoil_params = base_airfoil_params
        self.override_parameters = override_parameters

        self.override_parameter_start_idx = 0
        self.override_parameter_end_idx = self.base_airfoil_params.n_overrideable_parameters
        if self.override_parameters is not None:
            self.base_airfoil_params.override(
                self.override_parameters[self.override_parameter_start_idx:self.override_parameter_end_idx])
        self.override_parameter_start_idx += self.base_airfoil_params.n_overrideable_parameters

        self.c = base_airfoil_params.c
        self.alf = base_airfoil_params.alf
        self.R_le = base_airfoil_params.R_le
        self.L_le = base_airfoil_params.L_le
        self.r_le = base_airfoil_params.r_le
        self.phi_le = base_airfoil_params.phi_le
        self.psi1_le = base_airfoil_params.psi1_le
        self.psi2_le = base_airfoil_params.psi2_le
        self.L1_te = base_airfoil_params.L1_te
        self.L2_te = base_airfoil_params.L2_te
        self.theta1_te = base_airfoil_params.theta1_te
        self.theta2_te = base_airfoil_params.theta2_te
        self.t_te = base_airfoil_params.t_te
        self.r_te = base_airfoil_params.r_te
        self.phi_te = base_airfoil_params.phi_te

        self.C = []
        self.free_points = {}
        self.param_dicts = {}
        self.coords = None
        self.curvature = None
        self.area = None
        self.needs_update = True

        self.anchor_point_tuple = anchor_point_tuple

        if self.override_parameters is not None:
            for anchor_point in self.anchor_point_tuple:
                if self.base_airfoil_params.non_dim_by_chord:
                    anchor_point.length_scale_dimension = self.base_airfoil_params.c.value
                self.override_parameter_end_idx = self.override_parameter_start_idx + \
                                                  anchor_point.n_overrideable_parameters
                anchor_point.override(
                    self.override_parameters[self.override_parameter_start_idx:self.override_parameter_end_idx])
                self.override_parameter_start_idx += anchor_point.n_overrideable_parameters

        self.free_point_tuple = free_point_tuple

        if self.override_parameters is not None:
            for free_point in self.free_point_tuple:
                if self.base_airfoil_params.non_dim_by_chord:
                    free_point.length_scale_dimension = self.base_airfoil_params.c.value
                self.override_parameter_end_idx = self.override_parameter_start_idx + \
                                                  free_point.n_overrideable_parameters
                free_point.override(
                    self.override_parameters[self.override_parameter_start_idx:self.override_parameter_end_idx])
                self.override_parameter_start_idx += free_point.n_overrideable_parameters

        self.anchor_points = {'te_1': self.c.value * np.array([1, 0]) + self.r_te.value * self.t_te.value *
                                      np.array([np.cos(np.pi / 2 + self.phi_te.value),
                                                np.sin(np.pi / 2 + self.phi_te.value)]),
                              'le': np.array([0.0, 0.0]),
                              'te_2': self.c.value * np.array([1, 0]) -
                                      (1 - self.r_te.value) * self.t_te.value *
                                      np.array([np.cos(np.pi / 2 + self.phi_te.value),
                                                np.sin(np.pi / 2 + self.phi_te.value)])}
        self.anchor_point_order = ['te_1', 'le', 'te_2']
        self.anchor_point_array = np.array([])

        self.N = {
            'te_1': 4,
            'le': 4
        }

        self.control_points = np.array([])
        self.n_control_points = len(self.control_points)

        self.g1_minus_points, self.g1_plus_points = self.init_g1_points()
        self.g2_minus_points, self.g2_plus_points = self.init_g2_points()

        self.update()

    def init_g1_points(self):

        g1_minus_points = {
            'te_2': self.anchor_points['te_2'] +
                  self.L2_te.value * np.array([-np.cos(self.theta2_te.value),
                                               -np.sin(self.theta2_te.value)]),
            'le': self.anchor_points['le'] +
                  self.r_le.value * self.L_le.value *
                  np.array([np.cos(np.pi / 2 + self.phi_le.value),
                            np.sin(np.pi / 2 + self.phi_le.value)])
        }

        g1_plus_points = {
            'te_1': self.anchor_points['te_1'] +
                    self.L1_te.value * np.array([-np.cos(self.theta1_te.value),
                                                 np.sin(self.theta1_te.value)]),
            'le': self.anchor_points['le'] -
                  (1 - self.r_le.value) * self.L_le.value *
                  np.array([np.cos(np.pi / 2 + self.phi_le.value),
                            np.sin(np.pi / 2 + self.phi_le.value)])
        }

        return g1_minus_points, g1_plus_points

    def init_g2_points(self):
        g2_minus_point_le, g2_plus_point_le = self.set_curvature_le()

        g2_minus_points = {
            'le': g2_minus_point_le
        }

        g2_plus_points = {
            'le': g2_plus_point_le
        }

        return g2_minus_points, g2_plus_points

    def set_slope(self, anchor_point: AnchorPoint):
        phi = anchor_point.phi.value
        r = anchor_point.r.value
        L = anchor_point.L.value

        if self.anchor_point_order.index(anchor_point.name) < self.anchor_point_order.index('le'):
            self.g1_minus_points[anchor_point.name] = \
                self.anchor_points[anchor_point.name] + r * L * np.array([np.cos(phi), np.sin(phi)])
            self.g1_plus_points[anchor_point.name] = \
                self.anchor_points[anchor_point.name] - (1 - r) * L * np.array([np.cos(phi), np.sin(phi)])
        else:
            self.g1_minus_points[anchor_point.name] = \
                self.anchor_points[anchor_point.name] - r * L * np.array([np.cos(phi), np.sin(phi)])
            self.g1_plus_points[anchor_point.name] = \
                self.anchor_points[anchor_point.name] + (1 - r) * L * np.array([np.cos(phi), np.sin(phi)])
        return self.g1_minus_points, self.g1_plus_points

    def set_curvature_le(self):
        if self.R_le.value == np.inf:
            g2_minus_point = self.g1_minus_points['le']
            g2_plus_point = self.g1_plus_points['le']
        else:
            n1, n2 = self.N[self.anchor_point_order[self.anchor_point_order.index('le') - 1]], self.N['le']
            theta1, theta2 = self.psi1_le.value, -self.psi2_le.value
            x0, y0 = self.anchor_points['le'][0], self.anchor_points['le'][1]

            x_m1, y_m1 = self.g1_minus_points['le'][0], self.g1_minus_points['le'][1]
            g2_minus_point = np.zeros(2)
            g2_minus_point[0] = x_m1 - 1 / self.R_le.value * ((x0 - x_m1) ** 2 + (y0 - y_m1) ** 2) ** (3/2) / (
                                1 - 1 / n1) / ((x_m1 - x0) * np.tan(theta1) + y0 - y_m1)
            g2_minus_point[1] = np.tan(theta1) * (g2_minus_point[0] - x_m1) + y_m1

            x_p1, y_p1 = self.g1_plus_points['le'][0], self.g1_plus_points['le'][1]
            g2_plus_point = np.zeros(2)
            g2_plus_point[0] = x_p1 - 1 / self.R_le.value * ((x_p1 - x0) ** 2 + (y_p1 - y0) ** 2) ** (3/2) / (
                               1 - 1 / n2) / ((x0 - x_p1) * np.tan(theta2) + y_p1 - y0)
            g2_plus_point[1] = np.tan(theta2) * (g2_plus_point[0] - x_p1) + y_p1

        return g2_minus_point, g2_plus_point

    def set_curvature(self, anchor_point: AnchorPoint):
        R = anchor_point.R.value
        if R == np.inf:
            self.g2_minus_points[anchor_point.name] = self.g1_minus_points[anchor_point.name]
            self.g2_plus_points[anchor_point.name] = self.g1_plus_points[anchor_point.name]
        else:
            n1, n2 = self.N[self.anchor_point_order[self.anchor_point_order.index(anchor_point.name) - 1]], \
                     self.N[anchor_point.name]
            if R > 0:
                theta1, theta2 = anchor_point.psi1.value, -anchor_point.psi2.value
            else:
                theta1, theta2 = np.pi - anchor_point.psi1.value, np.pi + anchor_point.psi2.value
            x0, y0 = anchor_point.xy[0], anchor_point.xy[1]

            x_m1, y_m1 = self.g1_minus_points[anchor_point.name][0], self.g1_minus_points[anchor_point.name][1]
            g2_minus_point = np.zeros(2)
            g2_minus_point[0] = x_m1 - 1 / R * ((x0 - x_m1) ** 2 + (y0 - y_m1) ** 2) ** (3 / 2) / (
                    1 - 1 / n1) / ((x_m1 - x0) * np.tan(theta1) + y0 - y_m1)
            g2_minus_point[1] = np.tan(theta1) * (g2_minus_point[0] - x_m1) + y_m1

            x_p1, y_p1 = self.g1_plus_points[anchor_point.name][0], self.g1_plus_points[anchor_point.name][1]
            g2_plus_point = np.zeros(2)
            g2_plus_point[0] = x_p1 - 1 / R * ((x_p1 - x0) ** 2 + (y_p1 - y0) ** 2) ** (3 / 2) / (
                    1 - 1 / n2) / ((x0 - x_p1) * np.tan(theta2) + y_p1 - y0)
            g2_plus_point[1] = np.tan(theta2) * (g2_plus_point[0] - x_p1) + y_p1

            self.g2_minus_points[anchor_point.name] = g2_minus_point
            self.g2_plus_points[anchor_point.name] = g2_plus_point

        return self.g2_minus_points, self.g2_plus_points

    def extract_parameters(self):

        self.params = [var.value for var in vars(self.base_airfoil_params).values()
                       if isinstance(var, Param) and var.active and not var.linked]

        self.bounds = [[var.bounds[0], var.bounds[1]] for var in vars(self.base_airfoil_params).values()
                       if isinstance(var, Param) and var.active and not var.linked]

        for anchor_point in self.anchor_point_tuple:

            self.params.extend([var.value for var in vars(anchor_point).values()
                                if isinstance(var, Param) and var.active and not var.linked])

            self.bounds.extend([[var.bounds[0], var.bounds[1]] for var in vars(anchor_point).values()
                                if isinstance(var, Param) and var.active and not var.linked])

        for free_point in self.free_point_tuple:

            self.params.extend([var.value for var in vars(free_point).values()
                                if isinstance(var, Param) and var.active and not var.linked])

            self.bounds.extend([[var.bounds[0], var.bounds[1]] for var in vars(free_point).values()
                                if isinstance(var, Param) and var.active and not var.linked])

    # def inject_parameters(self):
    #
    #     param_idx = 0
    #
    #     # for obj in [var for var in vars(self.base_airfoil_params).values()
    #     #             if isinstance(var, Param) and var.active and not var.linked]:
    #     for key, var in vars(self.base_airfoil_params).items():
    #         if isinstance(var, Param) and var.active and not var.linked:
    #             print(f"params[param_idx] = {self.override_parameters[param_idx]}")
    #             setattr(var, 'value', self.override_parameters[param_idx])
    #             print(var.value)
    #             param_idx += 1
    #
    #     # print(f"c.value = {getattr(self.c, 'value')}")
    #     #
    #     # for anchor_point in self.anchor_point_tuple:
    #     #
    #     #     for obj in [var for var in vars(anchor_point).values()
    #     #                 if isinstance(var, Param) and var.active and not var.linked]:
    #     #         obj.value = self.override_parameters[param_idx]
    #     #         print(obj.value)
    #     #         param_idx += 1
    #     #
    #     # for free_point in self.free_point_tuple:
    #     #
    #     #     for obj in [var for var in vars(free_point).values()
    #     #                 if isinstance(var, Param) and var.active and not var.linked]:
    #     #         obj.value = self.override_parameters[param_idx]
    #     #         print(obj.value)
    #     #         param_idx += 1

    def order_control_points(self):
        self.control_points = np.array([])
        for idx, anchor_point in enumerate(self.anchor_point_order):

            if idx == 0:
                self.control_points = np.append(self.control_points, self.anchor_points[anchor_point])
                self.control_points = np.row_stack((self.control_points, self.g1_plus_points[anchor_point]))
            else:
                if anchor_point in self.g2_minus_points:
                    self.control_points = np.row_stack((self.control_points, self.g2_minus_points[anchor_point]))
                self.control_points = np.row_stack((self.control_points, self.g1_minus_points[anchor_point]))
                self.control_points = np.row_stack((self.control_points, self.anchor_points[anchor_point]))
                if anchor_point in self.g1_plus_points:
                    self.control_points = np.row_stack((self.control_points, self.g1_plus_points[anchor_point]))
                if anchor_point in self.g2_plus_points:
                    self.control_points = np.row_stack((self.control_points, self.g2_plus_points[anchor_point]))

            if anchor_point in self.free_points:
                if len(self.free_points[anchor_point]) > 0:
                    for fp_idx in range(len(self.free_points[anchor_point])):
                        self.control_points = \
                            np.row_stack((self.control_points, self.free_points[anchor_point][fp_idx, :]))

        self.n_control_points = len(self.control_points)
        return self.control_points, self.n_control_points

    def add_free_point(self, free_point: FreePoint):
        """
        Adds a free point (and 2 degrees of freedom) to a given Bezier curve (defined by the previous_anchor_point)
        :param free_point:
        :return:
        """
        if free_point.previous_anchor_point not in self.free_points.keys():
            self.free_points[free_point.previous_anchor_point] = np.array([])
        if len(self.free_points[free_point.previous_anchor_point]) == 0:
            self.free_points[free_point.previous_anchor_point] = free_point.xy.reshape((1, 2))
        else:
            self.free_points[free_point.previous_anchor_point] = np.vstack(
                (self.free_points[free_point.previous_anchor_point], free_point.xy))

        # Increment the order of the modified Bézier curve
        self.N[free_point.previous_anchor_point] += 1
        self.needs_update = True

    def add_anchor_point(self, anchor_point: AnchorPoint):
        """
        Adds an anchor point between two anchor points, builds the associated control point branch, and inserts the
        control point branch into the set of control points.
        :param anchor_point:
        :return:
        """
        self.anchor_point_order.insert(self.anchor_point_order.index(anchor_point.previous_anchor_point) + 1,
                                       anchor_point.name)
        self.anchor_points[anchor_point.name] = anchor_point.xy
        self.set_slope(anchor_point)
        if self.anchor_point_order.index(anchor_point.name) > self.anchor_point_order.index('le'):
            self.N['le'] = 5  # Set the order of the Bezier curve after the leading edge to 5
            self.N[self.anchor_point_order[-2]] = 4  # Set the order of the last Bezier curve to 4
        else:
            self.N[anchor_point.name] = 5  # Set the order of the Bezier curve after the anchor point to 5
        self.set_curvature(anchor_point)
        self.needs_update = True

    def add_anchor_points(self):
        for anchor_point in self.anchor_point_tuple:
            if anchor_point.name not in self.anchor_point_order:
                self.add_anchor_point(anchor_point)
        self.needs_update = True

    def add_free_points(self):
        for free_point in self.free_point_tuple:
            self.add_free_point(free_point)
        self.needs_update = True

    def update_anchor_point_array(self):
        for key in self.anchor_point_order:
            xy = self.anchor_points[key]
            if key == 'te_1':
                self.anchor_point_array = xy
            else:
                self.anchor_point_array = np.row_stack((self.anchor_point_array, xy))

    def update(self):
        self.add_anchor_points()
        self.add_free_points()
        self.extract_parameters()
        self.order_control_points()
        self.update_anchor_point_array()
        self.rotate(-self.alf.value)
        self.generate_airfoil_coordinates()
        self.needs_update = False

    def override(self, parameters):
        self.__init__(self.nt, self.base_airfoil_params, self.anchor_point_tuple, self.free_point_tuple,
                      override_parameters=parameters)

    # Need to incorporate into Airfoil().update() method
    def translate(self, dx: float, dy: float):
        self.control_points[:, 0] += dx
        self.control_points[:, 1] += dy
        self.needs_update = True
        return self.control_points

    def rotate(self, angle: float):
        rot_mat = np.array([[np.cos(angle), -np.sin(angle)],
                            [np.sin(angle), np.cos(angle)]])
        self.control_points = (rot_mat @ self.control_points.T).T
        self.anchor_point_array = (rot_mat @ self.anchor_point_array.T).T
        self.needs_update = True
        return self.control_points

    def generate_airfoil_coordinates(self):
        if self.C:
            self.C = []
        P_start_idx = 0
        for idx in range(len(self.anchor_point_order) - 1):
            P_length = self.N[self.anchor_point_order[idx]] + 1
            P_end_idx = P_start_idx + P_length
            P = self.control_points[P_start_idx:P_end_idx, :]
            C = bezier(P, self.nt)
            self.C.append(C)
            P_start_idx = P_end_idx - 1
        coords = np.array([])
        curvature = np.array([])
        for idx in range(len(self.C)):
            if idx == 0:
                coords = np.column_stack((self.C[idx]['x'], self.C[idx]['y']))
                curvature = np.column_stack((self.C[idx]['x'], self.C[idx]['k']))
            else:
                coords = np.row_stack((coords, np.column_stack((self.C[idx]['x'][1:], self.C[idx]['y'][1:]))))
                curvature = np.row_stack((curvature, np.column_stack((self.C[idx]['x'][1:], self.C[idx]['k'][1:]))))
        self.coords = coords
        self.curvature = curvature
        return self.coords, self.C

    def compute_area(self):
        if self.needs_update:
            self.update()
        points_shapely = list(map(tuple, self.coords))
        polygon = Polygon(points_shapely)
        area = polygon.area
        self.area = area
        return area

    def check_self_intersection(self):
        if self.needs_update:
            self.update()
        points_shapely = list(map(tuple, self.coords))
        line_string = LineString(points_shapely)
        is_simple = line_string.is_simple
        return not is_simple

    def plot(self, plot_what: typing.Tuple[str, ...], fig: Figure = None, axs: Axes = None, show_plot: bool = True,
             save_plot: bool = False, save_path: str = None, plot_kwargs: typing.List[dict] = None,
             show_title: bool = True, show_legend: bool = True, figwidth: float = 10.0, figheight: float = 2.5,
             tight_layout: bool = True, axis_equal: bool = True):
        if self.needs_update:
            self.update()
        if fig is None and axs is None:
            fig, axs = plt.subplots(1, 1)

        for what_to_plot in plot_what:

            if what_to_plot == 'airfoil':
                for idx, C in enumerate(self.C):
                    if plot_kwargs is None:
                        if idx == 0:
                            axs.plot(C['x'], C['y'], color='cornflowerblue', label='airfoil')
                        else:
                            axs.plot(C['x'], C['y'], color='cornflowerblue')
                    else:
                        axs.plot(C['x'], C['y'], **plot_kwargs[idx])

            if what_to_plot == 'anchor-point-skeleton':
                if plot_kwargs is None:
                    axs.plot(self.anchor_point_array[:, 0], self.anchor_point_array[:, 1], ':x', color='black',
                             label='anchor point skeleton')
                else:
                    axs.plot(self.anchor_point_array[:, 0], self.anchor_point_array[:, 1], **plot_kwargs)

            if what_to_plot == 'control-point-skeleton':
                if plot_kwargs is None:
                    axs.plot(self.control_points[:, 0], self.control_points[:, 1], '--*', color='grey',
                             label='control point skeleton')
                else:
                    axs.plot(self.control_points[:, 0], self.control_points[:, 1], **plot_kwargs)
            if what_to_plot == 'chordline':
                if plot_kwargs is None:
                    axs.plot(np.array([0, self.c.value * np.cos(self.alf.value)]),
                             np.array([0, -self.c.value * np.sin(self.alf.value)]), '-.', color='indianred',
                             label='chordline')
                else:
                    axs.plot(np.array([0, self.c.value * np.cos(self.alf.value)]),
                             np.array([0, -self.c.value * np.sin(self.alf.value)]), **plot_kwargs)
            if what_to_plot == 'R-circles':
                line = [[0, self.R_le.value * np.cos(self.phi_le.value - self.alf.value)],
                        [0, self.R_le.value * np.sin(self.phi_le.value - self.alf.value)]]
                circle = plt.Circle((line[0][1], line[1][1]), self.R_le.value, fill=False, color='gold',
                                    label='R circle')
                axs.plot(line[0], line[1], color='gold')
                axs.add_patch(circle)
            if what_to_plot == 'curvature':
                if plot_kwargs is None:
                    axs.plot(self.curvature[:, 0], self.curvature[:, 1], color='cornflowerblue', label='curvature')
                else:
                    axs.plot(self.curvature[:, 0], self.curvature[:, 1], **plot_kwargs)

        if axis_equal:
            axs.set_aspect('equal', 'box')
        if show_title:
            area = self.compute_area()
            fig.suptitle(
                fr'Airfoil: $c={self.c.value:.3f}$, $\alpha={np.rad2deg(self.alf.value):.3f}^\circ$, $A={area:.5f}$')
        else:
            fig.suptitle(
                fr'Airfoil: $c={self.c.value:.3f}$, $\alpha={np.rad2deg(self.alf.value):.3f}^\circ$')
        if tight_layout:
            fig.tight_layout()
        fig.set_figwidth(figwidth)
        fig.set_figheight(figheight)
        if show_legend:
            axs.legend()
        if save_plot:
            fig.savefig(save_path)
        if show_plot:
            plt.show()
        return fig, axs


def bezier(P: np.ndarray, nt: int) -> dict:
    """
    ### Description:

    Computes the Bezier curve through the control points `P` according to
    $$\\vec{C}(t)=\\sum_{i=0}^n \\vec{P}_i B_{i,n}(t)$$ where \\(B_{i,n}(t)\\) is the Bernstein polynomial, given by
    $$B_{i,n}={n \\choose i} t^i (1-t)^{n-i}$$

    Also included are first derivative, second derivative, and curvature information. These are given by
    $$\\vec{C}'(t)=n \\sum_{i=0}^{n-1} (\\vec{P}_{i+1} - \\vec{P}_i B_{i,n-1}(t)$$
    $$\\vec{C}''(t)=n(n-1) \\sum_{i=0}^{n-2} (\\vec{P}_{i+2}-2\\vec{P}_{i+1}+\\vec{P}_i) B_{i,n-2}(t)$$
    $$\\kappa(t)=\\frac{C'_x(t) C''_y(t) - C'_y(t) C''_x(t)}{[(C'_x)^2(t) + (C'_y)^2(t)]^{3/2}}$$

    .. image:: bezier_curve.png
       :align: center

    ### Args:

    `P`: `np.ndarray` of `shape=(n+1, 2)`, where `n` is the order of the Bezier curve and `n+1` is the number of
    control points in the Bezier curve. The two columns represent the `x` and `y` components of the control points.

    `nt`: number of points in the `t` vector (defines the resolution of the curve)

    ### Returns:

    A dictionary of `numpy` arrays of `shape=nt` containing information related to the created Bezier curve:

    $$C_x(t), C_y(t), C'_x(t), C'_y(t), C''_x(t), C''_y(t), \\kappa(t)$$
    where the \\(x\\) and \\(y\\) subscripts represent the \\(x\\) and \\(y\\) components of the vector-valued function.
    """

    def nCr(n_, r):
        """
        ### Description:

        Simple function that computes the mathematical combination $$n \\choose r$$

        ### Args:

        `n_`: `n` written with a trailing underscore to avoid conflation with the order `n` of the Bezier curve

        `r'

        ### Returns

        $$n \\choose r$$
        """
        f = np.math.factorial
        return f(n_) / f(r) / f(n_ - r)

    t = np.linspace(0, 1, nt)
    C = {
        't': t,
        'x': 0,
        'y': 0,
        'px': 0,
        'py': 0,
        'ppx': 0,
        'ppy': 0
    }
    n = len(P)
    for i in range(n):
        # Calculate the x- and y-coordinates of the of the Bezier curve given the input vector t
        C['x'] = C['x'] + P[i, 0] * nCr(n - 1, i) * t ** i * (1 - t) ** (n - 1 - i)
        C['y'] = C['y'] + P[i, 1] * nCr(n - 1, i) * t ** i * (1 - t) ** (n - 1 - i)
    for i in range(n - 1):
        # Calculate the first derivatives of the Bezier curve with respect to t, that is C_x'(t) and C_y'(t). Here,
        # C_x'(t) is the x-component of the vector derivative dC(t)/dt, and C_y'(t) is the y-component
        C['px'] = C['px'] + (n - 1) * (P[i + 1, 0] - P[i, 0]) * nCr(n - 2, i) * t ** i * (1 - t) ** (
                n - 2 - i)
        C['py'] = C['py'] + (n - 1) * (P[i + 1, 1] - P[i, 1]) * nCr(n - 2, i) * t ** i * (1 - t) ** (
                n - 2 - i)
    for i in range(n - 2):
        # Calculate the second derivatives of the Bezier curve with respect to t, that is C_x''(t) and C_y''(t). Here,
        # C_x''(t) is the x-component of the vector derivative d^2C(t)/dt^2, and C_y''(t) is the y-component
        C['ppx'] = C['ppx'] + (n - 1) * (n - 2) * (P[i + 2, 0] - 2 * P[i + 1, 0] + P[i, 0]) * nCr(n - 3, i) * t ** (
            i) * (1 - t) ** (n - 3 - i)
        C['ppy'] = C['ppy'] + (n - 1) * (n - 2) * (P[i + 2, 1] - 2 * P[i + 1, 1] + P[i, 1]) * nCr(n - 3, i) * t ** (
            i) * (1 - t) ** (n - 3 - i)

        # Calculate the curvature of the Bezier curve (k = kappa = 1 / R, where R is the radius of curvature)
        C['k'] = (C['px'] * C['ppy'] - C['py'] * C['ppx']) / (C['px'] ** 2 + C['py'] ** 2) ** (3 / 2)

    return C


def main():

    base_airfoil_params = BaseAirfoilParams(c=Param(5.0),
                                            alf=Param(np.deg2rad(5.0)),
                                            R_le=Param(0.06, 'length'),
                                            L_le=Param(0.08, 'length'),
                                            r_le=Param(0.6),
                                            phi_le=Param(np.deg2rad(5.0)),
                                            psi1_le=Param(np.deg2rad(10.0)),
                                            psi2_le=Param(np.deg2rad(15.0)),
                                            L1_te=Param(0.25, 'length'),
                                            L2_te=Param(0.3, 'length'),
                                            theta1_te=Param(np.deg2rad(2.0)),
                                            theta2_te=Param(np.deg2rad(2.0)),
                                            t_te=Param(0.0, 'length'),
                                            r_te=Param(0.5),
                                            phi_te=Param(np.deg2rad(0.0)),
                                            non_dim_by_chord=True
                                            )

    anchor_point1 = AnchorPoint(x=Param(0.55, units='length'),
                                y=Param(0.05, units='length'),
                                name='anchor-top',
                                previous_anchor_point='te_1',
                                L=Param(0.1, units='length'),
                                R=Param(-0.3, units='length'),
                                r=Param(0.5),
                                phi=Param(np.deg2rad(0.0)),
                                psi1=Param(np.deg2rad(45.0)),
                                psi2=Param(np.deg2rad(45.0)),
                                length_scale_dimension=base_airfoil_params.c.value
                                )

    anchor_point2 = AnchorPoint(x=Param(0.35, units='length'),
                                y=Param(-0.02, units='length'),
                                name='anchor-bottom',
                                previous_anchor_point='le',
                                L=Param(0.13, units='length'),
                                R=Param(0.4, units='length'),
                                r=Param(0.7),
                                phi=Param(np.deg2rad(0.0)),
                                psi1=Param(np.deg2rad(75.0)),
                                psi2=Param(np.deg2rad(75.0)),
                                length_scale_dimension=base_airfoil_params.c.value
                                )

    anchor_point_tuple = (anchor_point1, anchor_point2)

    free_point1 = FreePoint(x=Param(0.15, units='length'),
                            y=Param(0.015, units='length'),
                            previous_anchor_point='le',
                            length_scale_dimension=base_airfoil_params.c.value)

    free_point2 = FreePoint(x=Param(0.58, units='length'),
                            y=Param(0.0, units='length'),
                            previous_anchor_point='anchor-bottom',
                            length_scale_dimension=base_airfoil_params.c.value)

    free_point3 = FreePoint(x=Param(0.3, units='length'),
                            y=Param(0.07, units='length'),
                            previous_anchor_point='anchor-top',
                            length_scale_dimension=base_airfoil_params.c.value)

    free_point_tuple = (free_point1, free_point2, free_point3)

    airfoil = Airfoil(number_coordinates=100,
                      base_airfoil_params=base_airfoil_params,
                      anchor_point_tuple=anchor_point_tuple,
                      free_point_tuple=free_point_tuple)

    parameters = [5.0, 0.08726646259971647, 0.06, 0.08, 0.6, 0.08726646259971647, 0.17453292519943295,
                  0.2617993877991494, 0.25, 0.3, 0.03490658503988659, 0.03490658503988659, 0.0, 0.5, 0.0, 0.55, 0.05,
                  0.1, -0.3, 0.5, 0.0, 0.7853981633974483, 0.7853981633974483, 0.35, -0.02, 0.13, 0.4, 0.7, 0.0,
                  1.3089969389957472, 1.3089969389957472, 0.15, 0.015, 0.58, 0.0, 0.3, 0.07]

    # airfoil.override(parameters)

    self_intersecting = airfoil.check_self_intersection()
    print(f"Self-intersecting? {self_intersecting}")

    airfoil.plot(('airfoil', 'control-point-skeleton'))


if __name__ == '__main__':
    main()
