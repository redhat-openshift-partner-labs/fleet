from pathlib import Path


def test_runtime_image_installs_certificate_authority_bundle():
    dockerfile = Path(__file__).parents[2] / "Dockerfile"
    runtime_stage = dockerfile.read_text(encoding="utf-8").split(
        "FROM registry.access.redhat.com/ubi9-minimal:latest", 1
    )[1]
    runtime_install = runtime_stage.split("COPY --from=build", 1)[0]

    assert "ca-certificates" in runtime_install
