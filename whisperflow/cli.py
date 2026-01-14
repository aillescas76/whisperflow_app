"""Command-line interface for Whisperflow."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

from whisperflow.config import apply_overrides, load_config
from whisperflow.errors import ConfigError, WhisperflowRuntimeError, UserInputError, format_error
from whisperflow.logging_utils import setup_logging

DEFAULT_CONFIG_PATH = Path("config") / "config.json"
logger = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Whisperflow CLI entrypoint."""
    parser = _build_parser()
    try:
        cleaned_argv, config_path = _extract_config_arg(argv)
        args = parser.parse_args(cleaned_argv)
        args.config = config_path
        overrides = _collect_overrides(args)

        if args.command == "status":
            _handle_status()
            return 0

        config = load_config(args.config)
        setup_logging(config)
        logger.debug("Loaded config from %s", args.config)

        if args.command == "start":
            merged_config = apply_overrides(config, overrides)
            _handle_start(merged_config)
            return 0
        if args.command == "stop":
            merged_config = apply_overrides(config, overrides)
            _handle_stop(merged_config)
            return 0
        if args.command == "transcribe":
            _handle_transcribe(args.input_path, config, overrides)
            return 0
        if args.command == "batch":
            _handle_batch(args.input_dir, config, overrides)
            return 0
    except (ConfigError, UserInputError, WhisperflowRuntimeError) as exc:
        print(format_error(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(format_error(exc), file=sys.stderr)
        return 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    common_parser = argparse.ArgumentParser(add_help=False)
    _add_common_options(common_parser)

    parser = argparse.ArgumentParser(
        prog="whisperflow",
        description="Whisperflow-style offline transcription tools.",
        parents=[common_parser],
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to config file (default: config/config.json).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "start",
        help="Start live capture via daemon.",
        parents=[common_parser],
    )

    subparsers.add_parser(
        "stop",
        help="Stop live capture via daemon.",
        parents=[common_parser],
    )

    subparsers.add_parser(
        "status",
        help="Show daemon status.",
        parents=[common_parser],
    )

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe a single audio file.",
        parents=[common_parser],
    )
    transcribe_parser.add_argument("input_path", help="Path to the audio file.")

    batch_parser = subparsers.add_parser(
        "batch",
        help="Transcribe all audio files in a folder.",
        parents=[common_parser],
    )
    batch_parser.add_argument("input_dir", help="Folder containing audio files.")

    return parser


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=None, help="Model size: small, medium, large-v3.")
    parser.add_argument("--language", default=None, help="Language code or 'auto'.")
    parser.add_argument("--task", default=None, help="Task: transcribe or translate.")
    parser.add_argument("--output_format", default=None, help="Output format: txt, srt, vtt, json.")
    parser.add_argument("--output_dir", default=None, help="Directory for output files.")


def _collect_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if args.model is not None:
        overrides["model"] = args.model
    if args.language is not None:
        overrides["language"] = args.language
    if args.task is not None:
        overrides["task"] = args.task
    if args.output_format is not None:
        overrides["output_format"] = args.output_format
    if args.output_dir is not None:
        overrides["output_dir"] = args.output_dir
    return overrides


def _extract_config_arg(argv: Sequence[str] | None) -> tuple[list[str], str]:
    """Allow --config to appear before or after subcommands."""
    if argv is None:
        argv_list = list(sys.argv[1:])
    else:
        argv_list = list(argv)

    config_path = str(DEFAULT_CONFIG_PATH)
    cleaned: list[str] = []
    index = 0

    while index < len(argv_list):
        value = argv_list[index]
        if value == "--config":
            if index + 1 >= len(argv_list):
                raise UserInputError("Missing value for --config.")
            config_path = argv_list[index + 1]
            if not config_path:
                raise UserInputError("Config path cannot be empty.")
            index += 2
            continue
        if value.startswith("--config="):
            config_path = value.split("=", 1)[1]
            if not config_path:
                raise UserInputError("Config path cannot be empty.")
            index += 1
            continue

        cleaned.append(value)
        index += 1

    return cleaned, config_path


def _handle_start(config: dict[str, Any]) -> None:
    try:
        from whisperflow.daemon import start_daemon
    except ModuleNotFoundError as exc:
        raise WhisperflowRuntimeError("Live capture is not available yet.") from exc
    start_daemon(config)


def _handle_stop(config: dict[str, Any]) -> None:
    try:
        from whisperflow.daemon import stop_daemon
    except ModuleNotFoundError as exc:
        raise WhisperflowRuntimeError("Live capture is not available yet.") from exc
    stop_daemon(config)


def _handle_status() -> None:
    try:
        from whisperflow.daemon import show_status
    except ModuleNotFoundError as exc:
        raise WhisperflowRuntimeError("Live capture status is not available yet.") from exc
    show_status()


def _handle_transcribe(input_path: str, config: dict[str, Any], overrides: dict[str, Any]) -> None:
    try:
        from whisperflow.transcribe import run_transcribe
    except ModuleNotFoundError as exc:
        raise WhisperflowRuntimeError("File transcription is not available yet.") from exc
    run_transcribe(input_path, config, overrides)


def _handle_batch(input_dir: str, config: dict[str, Any], overrides: dict[str, Any]) -> None:
    try:
        from whisperflow.batch import run_batch
    except ModuleNotFoundError as exc:
        raise WhisperflowRuntimeError("Batch transcription is not available yet.") from exc
    run_batch(input_dir, config, overrides)


__all__ = ["main"]
