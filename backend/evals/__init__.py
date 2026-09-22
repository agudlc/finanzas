"""
`make eval`: what the agent says about one fixed month, against real Claude.

The test suite scripts the model, because behaviour has to be the same every
time it is asserted. This is the other half of that trade: one dataset, held
still, put in front of the real API once per trigger, so a change to the
prompt or to the tools can be read as a change in what the coach actually
says. Nothing here asserts anything — it prints, and a person judges.
"""
