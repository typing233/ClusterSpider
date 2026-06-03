import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

from clusterspider.core import ExecutionEngine, ModuleRegistry
from clusterspider.core.module_base import TargetType
from clusterspider.modules import ALL_MODULES
from clusterspider.storage import Database


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    if not verbose:
        logging.getLogger("asyncio").setLevel(logging.WARNING)


def detect_target_type(target: str) -> TargetType:
    ip_pattern = re.compile(
        r"^(\d{1,3}\.){3}\d{1,3}$"
    )
    if ip_pattern.match(target):
        return TargetType.IP
    return TargetType.DOMAIN


def build_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    for module_cls in ALL_MODULES:
        registry.register(module_cls())
    return registry


async def run_scan(target: str, target_type: TargetType, db_path: str, modules: list[str] | None = None):
    registry = build_registry()

    if modules:
        all_mods = registry.list_modules()
        for m in all_mods:
            if m.name not in modules:
                registry.unregister(m.name)

    engine = ExecutionEngine(registry)
    task = await engine.scan(target, target_type)

    db = Database(db_path)
    db.save_task(task)
    db.close()

    return task


def main():
    parser = argparse.ArgumentParser(
        prog="clusterspider",
        description="ClusterSpider - Modular Reconnaissance Framework",
    )
    parser.add_argument("target", nargs="?", help="Target domain or IP address")
    parser.add_argument("-t", "--type", choices=["domain", "ip"],
                        help="Target type (auto-detected if omitted)")
    parser.add_argument("-m", "--modules", nargs="+",
                        help="Specific modules to run (default: all applicable)")
    parser.add_argument("-o", "--output", help="Output file path (JSON)")
    parser.add_argument("--db", default="clusterspider.db",
                        help="SQLite database path (default: clusterspider.db)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose/debug logging")
    parser.add_argument("--list-modules", action="store_true",
                        help="List all available modules and exit")

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("clusterspider")

    if args.list_modules:
        registry = build_registry()
        print("\nAvailable modules:")
        print("-" * 60)
        for m in registry.list_modules():
            targets = ", ".join(t.value for t in m.supported_targets)
            print(f"  {m.name:<20} {m.description}")
            print(f"  {'':20} targets: [{targets}]  timeout: {m.timeout}s")
        print()
        return

    if not args.target:
        parser.error("target is required (unless using --list-modules)")

    if args.type:
        target_type = TargetType(args.type)
    else:
        target_type = detect_target_type(args.target)

    logger.info(f"Target: {args.target} (type: {target_type.value})")
    logger.info(f"Starting scan...")

    task = asyncio.run(run_scan(args.target, target_type, args.db, args.modules))

    output = task.summary()
    json_output = json.dumps(output, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).write_text(json_output)
        logger.info(f"Results written to {args.output}")
    else:
        print("\n" + "=" * 60)
        print("SCAN RESULTS")
        print("=" * 60)
        print(json_output)

    success = task.modules_completed
    failed = task.modules_failed
    total = task.modules_total
    print(f"\n[Summary] {success}/{total} modules succeeded, {failed} failed")
    print(f"[Task ID] {task.id}")
    print(f"[Database] Results saved to {args.db}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
