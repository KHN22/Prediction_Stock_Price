"""Run a registered adapter and emit its JSON result."""

import json
import sys

from mu import run as run_mu
from amzn import run as run_amzn
from mu_import import merge_inputs
from mu_online import fetch_inputs as fetch_mu
from amzn_online import fetch_inputs as fetch_amzn

MODELS = {"mu": run_mu, "amzn": run_amzn}
FETCHERS = {"mu": fetch_mu, "amzn": fetch_amzn}

if __name__ == "__main__":
    try:
        model = MODELS[sys.argv[1]]
        payload = json.load(sys.stdin)
        if len(sys.argv) > 2 and sys.argv[2] == "--online":
            files, sources = FETCHERS[sys.argv[1]](payload["base"], payload.get("macroTables"))
            result = model(files)
            result["sources"] = sources
            output = {"files": files, "result": result}
        elif len(sys.argv) > 2 and sys.argv[2] == "--merge":
            files = merge_inputs(payload["base"], payload["updates"])
            output = {"files": files, "result": model(files)}
        else:
            output = model(payload)
        print(json.dumps(output, allow_nan=False))
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
