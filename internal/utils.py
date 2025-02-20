import json
import re
import warnings
from pydantic import BaseModel
from enum import Enum
from pathlib import Path
from typing import Iterator, Optional

DEFAULT_DIRECTORY = Path(__file__).parent.parent


with warnings.catch_warnings():
    # This triggers some dumb warning in jupyter_core
    warnings.simplefilter("ignore")
    import jupytext
    import jupytext.config


class ExampleType(int, Enum):
    MODULE = 1
    ASSET = 2


class Example(BaseModel):
    type: ExampleType
    filename: str  # absolute filepath to example file
    module: Optional[
        str
    ]  # python import path, or none if file is not a py module.
    # TODO(erikbern): don't think the module is used (by docs or monitors)?
    metadata: Optional[dict]
    repo_filename: str  # git repo relative filepath
    cli_args: Optional[list]  # Full command line args to run it
    stem: Optional[str]  # stem of path


_RE_NEWLINE = re.compile(r"\r?\n")
_RE_FRONTMATTER = re.compile(r"^---$", re.MULTILINE)


def render_example_md(example: Example) -> str:
    """Render a Python code example to Markdown documentation format."""

    with open(example.filename) as f:
        content = f.read()

    lines = _RE_NEWLINE.split(content)
    markdown: list[str] = []
    code: list[str] = []
    for line in lines:
        if line == "#" or line.startswith("# "):
            if code:
                markdown.extend(["```python", *code, "```", ""])
                code = []
            markdown.append(line[2:])
        else:
            markdown.append("")
            if code or line:
                code.append(line)

    if code:
        markdown.extend(["```python", *code, "```", ""])

    text = "\n".join(markdown)
    if _RE_FRONTMATTER.match(text):
        # Strip out frontmatter from text.
        if match := _RE_FRONTMATTER.search(text, 4):
            text = text[match.end() :]
    return text


def gather_example_files(
    parents: list[str], subdir: Path, ignored: list[str], recurse: bool
) -> Iterator[Example]:
    config = jupytext.config.JupytextConfiguration(
        root_level_metadata_as_raw_cell=False
    )

    for filename in sorted(list(subdir.iterdir())):
        if filename.is_dir() and recurse:
            # Gather two-subdirectories deep, but no further.
            yield from gather_example_files(
                parents + [str(subdir.stem)], filename, ignored, recurse=False
            )
        else:
            filename_abs: str = str(filename.resolve())
            ext: str = filename.suffix
            if parents:
                repo_filename: str = (
                    f"{'/'.join(parents)}/{subdir.name}/{filename.name}"
                )
            else:
                repo_filename: str = f"{subdir.name}/{filename.name}"

            if ext == ".py" and filename.stem != "__init__":
                if parents:
                    parent_mods = ".".join(parents)
                    module = f"{parent_mods}.{subdir.stem}.{filename.stem}"
                else:
                    module = f"{subdir.stem}.{filename.stem}"
                data = jupytext.read(open(filename_abs), config=config)
                metadata = data["metadata"]["jupytext"].get(
                    "root_level_metadata", {}
                )
                cmd = metadata.get("cmd", ["modal", "run", repo_filename])
                args = metadata.get("args", [])
                yield Example(
                    type=ExampleType.MODULE,
                    filename=filename_abs,
                    metadata=metadata,
                    module=module,
                    repo_filename=repo_filename,
                    cli_args=(cmd + args),
                    stem=Path(filename_abs).stem,
                )
            elif ext in [".png", ".jpeg", ".jpg", ".gif", ".mp4"]:
                yield Example(
                    type=ExampleType.ASSET,
                    filename=filename_abs,
                    repo_filename=repo_filename,
                )
            else:
                ignored.append(str(filename))


def get_examples(
    directory: Path = DEFAULT_DIRECTORY, silent=False
) -> Iterator[Example]:
    """Yield all Python module files and asset files relevant to building modal.com/docs."""
    if not directory.exists():
        raise Exception(
            f"Can't find directory {directory}. You might need to clone the modal-examples repo there"
        )

    ignored = []
    for subdir in sorted(
        p
        for p in directory.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and not p.name.startswith("internal")
    ):
        yield from gather_example_files(
            parents=[], subdir=subdir, ignored=ignored, recurse=True
        )
    if not silent:
        print(f"Ignoring examples files: {ignored}")


def get_examples_json():
    examples = list(ex.dict() for ex in get_examples())
    return json.dumps(examples)


if __name__ == "__main__":
    for example in get_examples():
        print(example.json())
