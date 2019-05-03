from typing import Union

import torch
import torch.nn as nn

from torchgeometry.core import warp_affine, get_rotation_matrix2d


## utilities to compute affine matrices


def _compute_tensor_center(tensor: torch.Tensor) -> torch.Tensor:
    """Computes the center of tensor plane."""
    height, width = tensor.shape[-2:]
    center_x: float = float(width - 1) / 2
    center_y: float = float(height - 1) / 2
    center: torch.Tensor = torch.tensor([center_x, center_y],
        device=tensor.device, dtype=tensor.dtype)
    return center


def _compute_rotation_matrix(angle: torch.Tensor, center: torch.Tensor) -> torch.Tensor:
    """Computes a pure affine rotation matrix."""
    scale: torch.Tensor = torch.ones_like(angle)
    matrix: torch.Tensor = get_rotation_matrix2d(center, angle, scale)
    return matrix


def _compute_translation_matrix(translation: torch.Tensor) -> torch.Tensor:
    """Computes affine matrix for translation."""
    matrix: torch.Tensor = torch.eye(
        3, device=translation.device, dtype=translation.dtype)
    matrix = matrix.repeat(translation.shape[0], 1, 1)

    dx, dy = torch.chunk(translation, chunks=2, dim=-1)
    matrix[..., 0, 2:3] += dx
    matrix[..., 1, 2:3] += dy
    return matrix


def _compute_scaling_matrix(scale: torch.Tensor, center: torch.Tensor) -> torch.Tensor:
    """Computes affine matrix for scaling."""
    angle: torch.Tensor = torch.zeros_like(scale)
    matrix: torch.Tensor = get_rotation_matrix2d(center, angle, scale)
    return matrix


# based on:
# https://github.com/anibali/tvl/blob/master/src/tvl/transforms.py#L166

def affine(tensor: torch.Tensor, matrix: torch.Tensor) -> torch.Tensor:
    r"""Apply an affine transformation to the image.
    
    Args:
        tensor (torch.Tensor): The image tensor to be warped.
        matrix (torch.Tensor): The 2x3 affine transformation matrix.
    
    Returns:
        torch.Tensor: The warped image.
    """
    # warping needs data in the shape of BCHW
    is_unbatched: bool = tensor.ndimension() == 3
    if is_unbatched:
        tensor = torch.unsqueeze(tensor, dim=0)

    # we enforce broadcasting since by default grid_sample it does not
    # give support for that
    matrix = matrix.expand(tensor.shape[0], -1, -1)

    # warp the input tensor
    warped: torch.Tensor = warp_affine(tensor, matrix, tensor.shape[-2:])

    # return in the original shape
    if is_unbatched:
        warped = torch.squeeze(warped, dim=0)

    return warped


# based on:
# https://github.com/anibali/tvl/blob/master/src/tvl/transforms.py#L185

def rotate(tensor: torch.Tensor, angle: torch.Tensor,
           center: Union[None, torch.Tensor] = None) -> torch.Tensor:
    r"""Rotate the image anti-clockwise about the centre.
    
    Args:
        tensor (torch.Tensor): The image tensor to be rotated.
        angle (torch.Tensor): The angle through which to rotate.
        center (torch.Tensor): The center through which to rotate. The tensor
          must have a shape of :math:(B, 2), where B is batch size and last
          dimension contains cx and cy.
    Returns:
        torch.Tensor: The rotated image tensor.
    """
    if not torch.is_tensor(tensor):
        raise TypeError("Input tensor type is not a torch.Tensor. Got {}"
                        .format(type(tensor)))
    if not torch.is_tensor(angle):
        raise TypeError("Input angle type is not a torch.Tensor. Got {}"
                        .format(type(angle)))
    if center is not None and not torch.is_tensor(angle):
        raise TypeError("Input center type is not a torch.Tensor. Got {}"
                        .format(type(center)))
    if len(tensor.shape) not in (3, 4,):
        raise ValueError("Invalid tensor shape, we expect CxHxW or BxCxHxW. "
                         "Got: {}".format(tensor.shape))

    # compute the rotation center
    if center is None:
        center: torch.Tensor = _compute_tensor_center(tensor)

    # compute the rotation matrix
    # TODO: add broadcasting to get_rotation_matrix2d for center
    angle = angle.expand(tensor.shape[0])
    center = center.expand(tensor.shape[0], -1)
    rotation_matrix: torch.Tensor = _compute_rotation_matrix(angle, center)

    # warp using the affine transform
    return affine(tensor, rotation_matrix[..., :2, :3])


def translate(tensor: torch.Tensor, translation: torch.Tensor) -> torch.Tensor:
    r"""Translate the tensor in pixel units.
    Args:
        tensor (torch.Tensor): The image tensor to be translated.
        translation (torch.Tensor): tensor containing the amount of pixels to
          translate in the x and y direction. The tensor must have a shape of
          :math:(B, 2), where B is batch size, last dimension contains dx dy.
    Returns:
        torch.Tensor: The translated tensor.
    """
    if not torch.is_tensor(tensor):
        raise TypeError("Input tensor type is not a torch.Tensor. Got {}"
                        .format(type(tensor)))
    if not torch.is_tensor(translation):
        raise TypeError("Input translation type is not a torch.Tensor. Got {}"
                        .format(type(translation)))
    if len(tensor.shape) not in (3, 4,):
        raise ValueError("Invalid tensor shape, we expect CxHxW or BxCxHxW. "
                         "Got: {}".format(tensor.shape))

    # compute the translation matrix
    translation_matrix: torch.Tensor = _compute_translation_matrix(translation)

    # warp using the affine transform
    return affine(tensor, translation_matrix[..., :2, :3])


def scale(tensor: torch.Tensor, scale_factor: torch.Tensor,
          center: Union[None, torch.Tensor] = None) -> torch.Tensor:
    r"""Scales the input image.
    
    Args:
        tensor (torch.Tensor): The image tensor to be scaled.
        scale_factor (torch.Tensor): The scale factor apply.
        center (torch.Tensor): The center through which to rotate. The tensor
          must have a shape of :math:(B, 2), where B is batch size and last
          dimension contains cx and cy.
    Returns:
        torch.Tensor: The scaled tensor.
    """
    if not torch.is_tensor(tensor):
        raise TypeError("Input tensor type is not a torch.Tensor. Got {}"
                        .format(type(tensor)))
    if not torch.is_tensor(scale_factor):
        raise TypeError("Input scale_factor type is not a torch.Tensor. Got {}"
                        .format(type(scale_factor)))

    # compute the tensor center
    if center is None:
        center: torch.Tensor = _compute_tensor_center(tensor)

    # compute the rotation matrix
    # TODO: add broadcasting to get_rotation_matrix2d for center
    center = center.expand(tensor.shape[0], -1)
    scale_factor = scale_factor.expand(tensor.shape[0])
    scaling_matrix: torch.Tensor = _compute_scaling_matrix(scale_factor, center)

    # warp using the affine transform
    return affine(tensor, scaling_matrix[..., :2, :3])


class Rotate(nn.Module):
    r"""Rotate the tensor anti-clockwise about the centre.
    
    Args:
        angle (torch.Tensor): The angle through which to rotate.
        center (torch.Tensor): The center through which to rotate. The tensor
          must have a shape of :math:(B, 2), where B is batch size and last
          dimension contains cx and cy.
    Returns:
        torch.Tensor: The rotated tensor.
    """
    def __init__(self, angle: torch.Tensor,
            center: Union[None, torch.Tensor] = None) -> None:
        super(Rotate, self).__init__()
        self.angle: torch.Tensor = angle
        self.center: Union[None, torch.Tensor] = center

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        return rotate(input, self.angle, self.center)

    def __repr__(self):
        return self.__class__.__name__ + '(' \
            'angle={0}, center={1})' \
            .format(self.angle.item(), self.center)


class Translate(nn.Module):
    r"""Translate the tensor in pixel units.
    Args:
        translation (torch.Tensor): tensor containing the amount of pixels to
          translate in the x and y direction. The tensor must have a shape of
          :math:(B, 2), where B is batch size, last dimension contains dx dy.
    Returns:
        torch.Tensor: The translated tensor.
    """
    def __init__(self, translation: torch.Tensor) -> None:
        super(Translate, self).__init__()
        self.translation: torch.Tensor = translation

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        return translate(input, self.translation)

    def __repr__(self):
        return self.__class__.__name__ + '(' \
            'translation={0})'.format(self.translation)


class Scale(nn.Module):
    r"""Scale the tensor by a factor.
    
    Args:
        scale_factor (torch.Tensor): The scale factor apply.
        center (torch.Tensor): The center through which to rotate. The tensor
          must have a shape of :math:(B, 2), where B is batch size and last
          dimension contains cx and cy.
    Returns:
        torch.Tensor: The scaled tensor.
    """
    def __init__(self, scale_factor: torch.Tensor,
            center: Union[None, torch.Tensor] = None) -> None:
        super(Scale, self).__init__()
        self.scale_factor: torch.Tensor = scale_factor
        self.center: torch.Tensor = center

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        return scale(input, self.scale_factor, self.center)

    def __repr__(self):
        return self.__class__.__name__ + '(' \
            'scale_factor={0}, center={1})'  \
            .format(self.scale_factor, self.center)
