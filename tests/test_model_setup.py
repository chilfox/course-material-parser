"""CLI seams for offline model setup and pre-flight refusals."""

import sys
from types import SimpleNamespace

import pytest

from conftest import assert_error, start_parse, write_settings
from course_material_parser import download_models_command
from course_material_parser import settings as settings_module
from course_material_parser.docling_conversion import DoclingConverter


@pytest.mark.parametrize(
    "device,formula", [("cpu", "CodeFormulaV2"), ("mps", "CodeFormulaV2 (MLX)")]
)
def test_missing_models_refuse_before_destination_checks_without_creating_anything(
    device, formula, run_parse, converter, library, settings_path, monkeypatch
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: True)
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace())
    write_settings(settings_path, library, device=device)
    converter.missing = [formula, "RapidOCR"]

    result = start_parse(run_parse, dest="../invalid")

    assert_error(result, "models_missing", formula, "RapidOCR", "download-models")
    assert converter.calls == []
    assert list(library.iterdir()) == []


def test_unavailable_device_precedes_model_check(
    run_parse, converter, settings_path, library, monkeypatch
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: False)
    write_settings(settings_path, library, device="cuda")
    converter.missing = ["CodeFormulaV2"]

    assert_error(start_parse(run_parse), "settings_error", "cuda", "not available")
    assert converter.model_checks == []


@pytest.mark.parametrize("flags,ocr", [((), False), (("--no-ocr",), False), (("--ocr",), True)])
def test_preflight_only_requests_ocr_for_explicit_ocr(run_parse, converter, flags, ocr):
    result = start_parse(run_parse, *flags)

    assert result.exit_code == 0, result.stderr
    assert converter.model_checks == [{"device": "cpu", "ocr": ocr}]


@pytest.mark.parametrize("device", ["cpu", "mps", "cuda"])
@pytest.mark.parametrize("allow_ocr", [False, True])
def test_download_and_preflight_agree_on_exact_models(
    device, allow_ocr, settings_path, library, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: True)
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace())
    write_settings(settings_path, library, f"allow_ocr = {str(allow_ocr).lower()}\n", device=device)
    directory = tmp_path / "cache" / "models"
    requested = []

    def download(model, target):
        requested.append((model.name, model.repo_id, model.revision, target))
        (target / model.folder).mkdir(parents=True)

    real = DoclingConverter(model_directory=directory)
    expected = [
        "docling-layout-heron",
        "TableFormer",
        "DocumentFigureClassifier-v2.5",
        "CodeFormulaV2 (MLX)" if device == "mps" else "CodeFormulaV2",
    ]
    if allow_ocr:
        expected.append("RapidOCR")
    assert real.missing_models(device=device, ocr=allow_ocr) == expected

    code = download_models_command.main(
        [], settings_path=settings_path, downloader=download, model_directory=directory
    )

    output = capsys.readouterr()
    assert code == 0, output.err
    assert requested == [
        (
            name,
            "mlx-community/CodeFormulaV2-mlx-bf16" if name == "CodeFormulaV2 (MLX)" else None,
            "f29c446f17d772025137fabc11288f07769c316f" if name == "CodeFormulaV2 (MLX)" else None,
            directory,
        )
        for name in expected
    ]
    assert real.missing_models(device=device, ocr=allow_ocr) == []
    assert output.err == ""
    for name in expected:
        assert f"Fetched {name}" in output.out
    assert output.out.endswith(f"{directory}\n")

    # Existing models, including unrelated models, survive a repeated setup.
    unrelated = directory / "unrelated-model" / "weights.bin"
    unrelated.parent.mkdir()
    unrelated.write_bytes(b"keep these weights")
    requested.clear()
    code = download_models_command.main(
        [], settings_path=settings_path, downloader=download, model_directory=directory
    )
    output = capsys.readouterr()
    assert code == 0, output.err
    assert requested == []
    for name in expected:
        assert f"Skipped {name} (already present)" in output.out
    assert unrelated.read_bytes() == b"keep these weights"


@pytest.mark.parametrize("command", ["parse", "download-models"])
def test_missing_mlx_runtime_refuses_mps_before_anything_is_created(
    command, run_parse, run_download, settings_path, library, converter, monkeypatch, tmp_path
):
    write_settings(settings_path, library, device="mps")
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))),
    )
    monkeypatch.setitem(sys.modules, "mlx_vlm", None)

    result = start_parse(run_parse) if command == "parse" else run_download()

    assert_error(result, "settings_error", "mps", "mlx-vlm", "uv sync")
    assert converter.model_checks == []
    assert converter.calls == []
    assert list(library.iterdir()) == []
    assert not (tmp_path / "models").exists()


def test_download_refuses_an_unavailable_device_without_fetching(
    run_download, settings_path, library, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings_module, "device_available", lambda device: False)
    write_settings(settings_path, library, device="cuda")

    assert_error(run_download(), "settings_error", "cuda", "not available")
    assert not (tmp_path / "models").exists()
