"""Separate question-only content computation and learned condition-only EOS control."""
import re
import torch
from torch import nn
from core import EOS


def condition_tokens(condition):
    match = re.fullmatch(r'EQ\(([1-9][0-9]{5}),([1-9][0-9]{5})\)', condition)
    if match is None:
        raise ValueError('Expected EQ with two six-digit operands')
    return [int(c) for c in match.group(1) + match.group(2)]


class ConditionChannel(nn.Module):
    def __init__(self, logit_gain=32.0):
        super().__init__()
        self.pair_scores = nn.Embedding(100, 1, dtype=torch.float32)
        nn.init.zeros_(self.pair_scores.weight)
        self.offset = nn.Parameter(torch.zeros((), dtype=torch.float32))
        self.register_buffer('gain', torch.tensor(float(logit_gain), dtype=torch.float32))

    def state(self, condition_ids):
        # Shared learned score for aligned character pairs. No truth comparison.
        indices = condition_ids[:, :6] * 10 + condition_ids[:, 6:]
        return self.pair_scores(indices).squeeze(-1).sum(-1) + self.offset

    def forward(self, condition_ids, permission_sign=1.0):
        state = self.state(condition_ids)
        delta = -self.gain * (state * permission_sign)
        return delta, state


class SeparatedContinuationModel(nn.Module):
    def __init__(self, content_model, channel):
        super().__init__()
        self.content = content_model.eval().requires_grad_(False)
        self.channel = channel

    def content_forward(self, question_ids, past_key_values=None):
        return self.content(input_ids=question_ids, past_key_values=past_key_values,
                            use_cache=True, logits_to_keep=1)

    def boundary(self, content_logits, condition_ids=None, first_step=True, permission_sign=1.0):
        if condition_ids is None or not first_step:
            return content_logits, None
        delta, state = self.channel(condition_ids, permission_sign=permission_sign)
        logits = content_logits.clone()
        logits[:, EOS] = (content_logits[:, EOS].float() + delta).to(logits.dtype)
        return logits, state

    def forward(self, question_ids, condition_ids=None, past_key_values=None,
                first_step=True, permission_sign=1.0):
        # Condition IDs cannot enter content_forward.
        output = self.content_forward(question_ids, past_key_values=past_key_values)
        stock = output.logits[:, -1, :]
        logits, state = self.boundary(stock, condition_ids, first_step, permission_sign)
        return {'logits': logits, 'stock_logits': stock,
                'past_key_values': output.past_key_values, 'permission_state': state}


def ordinary_equal(left, right):
    return torch.equal(left[..., :EOS], right[..., :EOS]) and torch.equal(left[..., EOS+1:], right[..., EOS+1:])
