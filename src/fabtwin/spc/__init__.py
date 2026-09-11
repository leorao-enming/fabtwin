"""SPC / process-capability layer - Gate T2, Overview section 4.2.

Submodules:
    phase        - the Phase I/II split that every chart in this package goes through
    imr          - Individuals (X) and Moving Range chart
    ewma         - Exponentially Weighted Moving Average chart
    capability   - Cp/Cpk (within sigma) and Pp/Ppk (overall sigma)

Still missing from this package (T2 continued, not yet built):
Xbar-R/Xbar-S subgroup charts, CUSUM, and the Western Electric/Nelson rule
engine. Do not claim Gate T2 is complete until those land too - see the
Overview's evidence snapshot for current status.
"""
