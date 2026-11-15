"""HTTP resources for non-destructive song-cut projects."""

from pathlib import Path

from segment.editor_media import waveform
from segment.editor_projects import Projects
from segment.editor_tasks_http import analysis_results, export_resource, start_analysis


def dispatch_project(handler, method: str, route: str) -> None:
    projects = Projects(handler.jobs.store)
    identity, _, action = route.removeprefix("/api/projects").lstrip("/").partition("/")
    if not identity:
        _collection(handler, method, projects)
        return
    project = projects.get(identity)
    if method == "GET" and not action:
        handler._json(200, project)
    elif method == "PUT" and not action:
        handler._json(200, projects.save(identity, handler._payload()))
    elif method == "DELETE" and not action:
        handler._json(200, handler.jobs.delete_source(identity))
    elif method == "GET" and action == "source":
        _serve_media(handler, project)
    elif method == "GET" and action == "waveform":
        source = handler.jobs._ready(project["upload_id"])
        handler._json(200, waveform(Path(source["source_path"]), handler.jobs.root / "editor-cache", source["sha256"]))
    elif method == "POST" and action == "analyze":
        start_analysis(handler, project)
    elif method == "GET" and action.startswith("analysis/"):
        analysis_results(handler, project, action.removeprefix("analysis/"))
    elif action == "exports" or action.startswith("exports/"):
        export_resource(handler, project, method, action)
    else:
        handler._json(404, {"error": "Project resource does not exist"})


def _collection(handler, method: str, projects: Projects) -> None:
    if method == "GET":
        handler._json(200, {"projects": handler.jobs.store.list("projects")})
        return
    if method != "POST":
        handler._json(404, {"error": "Project resource does not exist"})
        return
    payload = handler._payload()
    if payload.keys() != {"upload_id"} or not isinstance(payload["upload_id"], str):
        raise ValueError("Expected upload_id")
    source = handler.jobs._ready(payload["upload_id"])
    project = projects.create(
        {
            "upload_id": source["id"],
            "name": source["name"],
            "duration": handler.jobs.result_services["duration"](Path(source["source_path"])),
        }
    )
    handler._json(201, project)


def _serve_media(handler, project: dict) -> None:
    source = handler.jobs._ready(project["upload_id"])
    path = Path(source["source_path"])
    mime = handler.jobs.upload_mime(source["id"])
    handler._serve_file(path, mime=mime)
