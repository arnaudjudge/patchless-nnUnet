from functools import reduce
from operator import mul

import torch


def linear_expectation(probs, values):
    # assert(len(values) == probs.ndimension() - 2)
    expectation = []
    for i in range(2, probs.ndimension()-1):
        # Marginalise probabilities
        marg = probs
        for j in range(probs.ndimension() - 2, 1, -1):
            if i != j:
                marg = marg.sum(j, keepdim=False)
        # Calculate expectation along axis `i`
        expectation.append(((marg.view(-1, marg.shape[-2]) * values[len(expectation)]).view(marg.shape)).sum(-2, keepdim=False))
    return torch.stack(expectation, -1)


def soft_argmax(heatmaps, normalized_coordinates=True):
    if normalized_coordinates:
        values = [normalized_linspace(d, dtype=heatmaps.dtype, device=heatmaps.device)
                  for d in heatmaps.size()[-3:-1]]
    else:
        values = [torch.arange(0, d, dtype=heatmaps.dtype, device=heatmaps.device)
                  for d in heatmaps.size()[-3:-1]]
    coords = linear_expectation(heatmaps, values)
    # We flip the tensor like this instead of using `coords.flip(-1)` because aten::flip is not yet
    # supported by the ONNX exporter.
    coords = torch.cat(tuple(reversed(coords.split(1, -1))), -1)
    return coords


def dsnt(heatmaps, **kwargs):
    """Differentiable spatial to numerical transform.

    Args:
        heatmaps (torch.Tensor): Spatial representation of locations

    Returns:
        Numerical coordinates corresponding to the locations in the heatmaps.
    """
    return soft_argmax(heatmaps, **kwargs)


def normalized_linspace(length, dtype=None, device=None):
    """Generate a vector with values ranging from -1 to 1.
    Note that the values correspond to the "centre" of each cell, so
    -1 and 1 are always conceptually outside the bounds of the vector.
    For example, if length = 4, the following vector is generated:
    ```text
     [ -0.75, -0.25,  0.25,  0.75 ]
     ^              ^             ^
    -1              0             1
    ```
    Args:
        length: The length of the vector
    Returns:
        The generated vector
    """
    if isinstance(length, torch.Tensor):
        length = length.to(device, dtype)
    first = -(length - 1.0) / length
    return torch.arange(length, dtype=dtype, device=device) * (2.0 / length) + first


def flat_softmax(inp):
    """Compute the softmax with all but the first two tensor dimensions combined."""
    orig_size = inp.size()
    # flat = inp.view(-1, reduce(mul, orig_size[2:-1]))
    # flat = torch.nn.functional.softmax(flat, -1)
    flat = inp.view(-1, orig_size[1], reduce(mul, orig_size[2:-1]), orig_size[-1])
    flat = torch.nn.functional.softmax(flat, -2)
    return flat.view(*orig_size)


def euclidean_losses(actual, target):
    """Calculate the Euclidean losses for multi-point samples.
    Each sample must contain `n` points, each with `d` dimensions. For example,
    in the MPII human pose estimation task n=16 (16 joint locations) and
    d=2 (locations are 2D).
    Args:
        actual (Tensor): Predictions (B x L x D)
        target (Tensor): Ground truth target (B x L x D)
    Returns:
        Tensor: Losses (B x L)
    """
    assert actual.size() == target.size(), 'input tensors must have the same size'
    return torch.norm(actual - target, p=2, dim=-1, keepdim=False)


def normalized_to_pixel_coordinates(coords, size):
    """Convert from normalized coordinates to pixel coordinates.
    Args:
        coords: Coordinate tensor, where elements in the last dimension are ordered as (x, y, ...).
        size: Number of pixels in each spatial dimension, ordered as (..., height, width).
    Returns:
        `coords` in pixel coordinates.
    """
    if torch.is_tensor(coords):
        size = coords.new_tensor(size).flip(-1)
    return 0.5 * ((coords + 1) * size - 1)


def pixel_to_normalized_coordinates(coords, size):
    """Convert from pixel coordinates to normalized coordinates.
    Args:
        coords: Coordinate tensor, where elements in the last dimension are ordered as (x, y, ...).
        size: Number of pixels in each spatial dimension, ordered as (..., height, width).
    Returns:
        `coords` in normalized coordinates.
    """
    if torch.is_tensor(coords):
        size = coords.new_tensor(size).flip(-1)
    return ((2 * coords + 1) / size) - 1
