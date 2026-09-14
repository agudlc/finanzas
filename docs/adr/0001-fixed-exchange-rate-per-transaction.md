# Fixed exchange rate stored on every USD transaction

Argentina has several dollar rates (official, blue, MEP, card) that move daily, so converting historical USD transactions with a live rate would rewrite the past and make monthly comparisons dishonest. Every USD transaction therefore stores its own ARS-per-USD rate and rate type. It starts as an automatic estimate and can be replaced once by the confirmed figure (e.g. the card statement). All conversions to the display currency use that stored rate, never a current one.

## Considered Options

- **Keep ARS and USD fully separate**: honest, but budgets and monthly results could never include USD spending.
- **Convert on read with the current rate**: simplest, but historical numbers change every day.
