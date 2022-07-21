# Copyright (c) OpenMMLab. All rights reserved.
from typing import Tuple, Union

import torch
import torch.nn as nn
from torch.autograd import Function
from torch.autograd.function import once_differentiable
from torch.nn.modules.utils import _pair

from ..utils import ext_loader

ext_module = ext_loader.load_ext(
    '_ext',
    ['prroi_pool_forward', 'prroi_pool_backward', 'prroi_pool_coor_backward'])


class PrRoIPoolFunction(Function):

    @staticmethod
    def symbolic(g, features, rois, output_size, spatial_scale):
        return g.op(
            'mmcv::PrRoIPool',
            features,
            rois,
            pooled_height_i=int(output_size[0]),
            pooled_width_i=int(output_size[1]),
            spatial_scale_f=float(spatial_scale))

    @staticmethod
    def forward(ctx,
                features: torch.Tensor,
                rois: torch.Tensor,
                output_size: Tuple,
                spatial_scale: float = 1.0) -> torch.Tensor:
        assert 'FloatTensor' in features.type() and 'FloatTensor' in rois.type(
        ), f'Precise RoI Pooling only takes float input, got {features.type()}'
        f' for features and {rois.type()} for rois.'

        pooled_height = int(output_size[0])
        pooled_width = int(output_size[1])
        spatial_scale = float(spatial_scale)

        features = features.contiguous()
        rois = rois.contiguous()
        output_shape = (rois.size(0), features.size(1), pooled_height,
                        pooled_width)
        output = features.new_zeros(output_shape)
        params = (pooled_height, pooled_width, spatial_scale)

        ext_module.prroi_pool_forward(features, rois, output, *params)
        ctx.params = params
        # everything here is contiguous.
        ctx.save_for_backward(features, rois, output)

        return output

    @staticmethod
    @once_differentiable
    def backward(
        ctx, grad_output: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, None, None, None]:
        features, rois, output = ctx.saved_tensors
        grad_input = grad_output.new_zeros(*features.shape)
        grad_coor = grad_output.new_zeros(*rois.shape)

        if features.requires_grad:
            grad_output = grad_output.contiguous()
            ext_module.prroi_pool_backward(grad_output, rois, grad_input,
                                           *ctx.params)
        if rois.requires_grad:
            grad_output = grad_output.contiguous()
            ext_module.prroi_pool_coor_backward(output, grad_output, features,
                                                rois, grad_coor, *ctx.params)

        return grad_input, grad_coor, None, None, None


prroi_pool = PrRoIPoolFunction.apply


class PrRoIPool(nn.Module):

    def __init__(self,
                 output_size: Union[int, tuple],
                 spatial_scale: float = 1.0):
        super().__init__()

        self.output_size = _pair(output_size)
        self.spatial_scale = float(spatial_scale)

    def forward(self, features: torch.Tensor,
                rois: torch.Tensor) -> torch.Tensor:
        return prroi_pool(features, rois, self.output_size, self.spatial_scale)

    def __repr__(self):
        s = self.__class__.__name__
        s += f'(output_size={self.output_size}, '
        s += f'spatial_scale={self.spatial_scale})'
        return s
