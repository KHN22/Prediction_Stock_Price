"""Run a registered adapter and emit its JSON result."""

import json
import sys

from mu import run
from mu_import import merge_inputs

MODELS = {"mu": run}

if __name__ == "__main__":
    try:
        model = MODELS[sys.argv[1]]
        payload = json.load(sys.stdin)
        if len(sys.argv) > 2 and sys.argv[2] == "--merge":
            files = merge_inputs(payload["base"], payload["updates"])
            output = {"files": files, "result": model(files)}
        else:
            output = model(payload)
        print(json.dumps(output, allow_nan=False))
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
