# es-pvpc

- Publisher: Red Eléctrica (REE). e-sios API https://api.esios.ree.es/indicators/1001 answered 206 without a token
  (indicator metadata); values normally need a personal token (ask consultasios@ree.es). apidatos.ree.es answered 200 (market prices).
- PVPC is indexed to the hourly wholesale price and 2.0TD has weekday/weekend periods (P1 punta, P2 llano, P3 valle),
  so the energy price is neither flat nor a fixed schedule: NOT expressible by this schema. Regulated access tolls and the
  power term are fixed and could be a later "partial" definition.
