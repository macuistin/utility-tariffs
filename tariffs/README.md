# tariffs/

One folder per service. Each is a complete store of its own, with its own indexes, so a client
reads only the service it wants. `docs/format.md` describes every field.

    tariffs/
      electricity/
        index.json                                   countries index (generated)
        unavailable.json                             countries with no rates yet (by hand)
        <cc>/index.json                              country values (by hand), then `providers` (generated)
        <cc>/<provider-id>/<tariff-id>/<n>.json      one tariff revision

Electricity is the only service held today. `docs/design.md` says how gas, water and combined
tariffs would be added.

After editing a tariff file or the top of a country index, run `python3 -m scripts.build`. Never
edit `providers` or `index.json` by hand, and never change a published revision: add the next
numbered file.
