import torch

from .shapley_tensor import ShapleyTensor


class GCDTensor(ShapleyTensor):
    def mul_contributions(self, *args, **kwargs):
        arg1, arg2 = args

        if isinstance(arg1, torch.Tensor):
            contributions = [
                torch.mul(arg1, contribution, **kwargs)
                for contribution in arg2.contributions
            ]
        elif isinstance(arg2, torch.Tensor):
            contributions = [
                torch.mul(contribution, arg2, **kwargs)
                for contribution in arg1.contributions
            ]
        else:
            contributions_sum = sum(arg1.contributions)
            contributions = [
                torch.mul(contributions_sum, contribution, **kwargs)
                for contribution in arg2.contributions
            ]

        return contributions
