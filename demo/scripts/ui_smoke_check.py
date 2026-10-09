import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

from ui.dashboard import (
    _default_instance,
    _load_evidence,
    _load_latest_result,
    _load_instance,
    _view_3d,
    _view_convergence,
    _view_path_map,
)


def main() -> None:
    print("imports ok")
    recs = _load_evidence()
    result = _load_latest_result() or {}
    inst = _load_instance(result.get("instance_id", "")) or _default_instance()
    print("recs:", len(recs))
    print("result keys:", len(result))
    print("instance nodes:", len(inst.get("nodes", [])) if inst else 0)
    fig1 = _view_path_map(result, inst)
    fig2 = _view_convergence(recs, result)
    fig4 = _view_3d(inst, result)
    print("fig1:", bool(fig1))
    print("fig2:", bool(fig2))
    print("fig4:", bool(fig4))
    print("UI smoke check passed")


if __name__ == "__main__":
    main()
