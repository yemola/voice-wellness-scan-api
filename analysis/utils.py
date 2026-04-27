import numpy as np

def mean(a):
    if not a:
        return 0
    return sum(a) / len(a)

def std(a):
    if len(a) < 2:
        return 0
    m = mean(a)
    s = sum((v - m) ** 2 for v in a)
    return (s / (len(a) - 1)) ** 0.5

def clamp(n, lo=0, hi=100):
    return max(lo, min(hi, n))

def lerp(x, x0, x1):
    if x1 == x0:
        return 0
    return (x - x0) / (x1 - x0)
