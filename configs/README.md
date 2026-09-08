# Configs

Version-controlled, human-readable configuration for everything a case run needs to
be reproducible: baseline recipe/tool/lot parameters, fault schedules, random seeds,
SPC method parameters (lambda/L/k/h/target), and case-study definitions.

Nothing here is generated — these are the frozen inputs that `make cases` reads.
Empty at P0; first configs land with Gate T1 (data dictionary + simulator).
