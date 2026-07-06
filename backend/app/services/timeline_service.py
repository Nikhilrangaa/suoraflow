"""Timeline service — clips, timelines, ordered items, and export."""
import csv
import io

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.asset import Asset
from app.models.clip import Clip, Timeline, TimelineItem
from app.models.project import Project
from app.schemas.timeline import (
    ClipCreate,
    ClipRead,
    TimelineCreate,
    TimelineItemCreate,
    TimelineItemMove,
    TimelineItemRead,
    TimelineRead,
)


# ---------------------------------------------------------------------------
# Clips
# ---------------------------------------------------------------------------

def _clip_to_read(clip: Clip, asset_filename: str) -> ClipRead:
    return ClipRead(
        id=clip.id,
        project_id=clip.project_id,
        asset_id=clip.asset_id,
        asset_filename=asset_filename,
        start=clip.start,
        end=clip.end,
        label=clip.label,
        created_at=clip.created_at,
    )


def create_clip(session: Session, project_id: str, data: ClipCreate) -> ClipRead:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    asset = session.get(Asset, data.asset_id)
    if asset is None or asset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Asset not found in this project")
    if asset.duration is not None and data.start >= asset.duration:
        raise HTTPException(
            status_code=400, detail="Clip start is beyond the asset duration"
        )

    clip = Clip(
        project_id=project_id,
        asset_id=data.asset_id,
        start=data.start,
        end=data.end,
        label=data.label.strip(),
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _clip_to_read(clip, asset.original_filename)


def list_clips(session: Session, project_id: str) -> list[ClipRead]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = session.exec(
        select(Clip, Asset)
        .join(Asset, Asset.id == Clip.asset_id)  # type: ignore[arg-type]
        .where(Clip.project_id == project_id)
        .order_by(Clip.created_at.desc())  # type: ignore[arg-type]
    ).all()
    return [_clip_to_read(c, a.original_filename) for c, a in rows]


# ---------------------------------------------------------------------------
# Timelines
# ---------------------------------------------------------------------------

def _timeline_to_read(session: Session, timeline: Timeline) -> TimelineRead:
    rows = session.exec(
        select(TimelineItem, Clip, Asset)
        .join(Clip, Clip.id == TimelineItem.clip_id)  # type: ignore[arg-type]
        .join(Asset, Asset.id == Clip.asset_id)  # type: ignore[arg-type]
        .where(TimelineItem.timeline_id == timeline.id)
        .order_by(TimelineItem.position)  # type: ignore[arg-type]
    ).all()
    items = [
        TimelineItemRead(
            id=item.id,
            position=item.position,
            clip=_clip_to_read(clip, asset.original_filename),
        )
        for item, clip, asset in rows
    ]
    total = round(sum(i.clip.end - i.clip.start for i in items), 3)
    return TimelineRead(
        id=timeline.id,
        project_id=timeline.project_id,
        name=timeline.name,
        created_at=timeline.created_at,
        items=items,
        total_duration=total,
    )


def create_timeline(
    session: Session, project_id: str, data: TimelineCreate
) -> TimelineRead:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    name = data.name.strip() or "Rough Cut"
    timeline = Timeline(project_id=project_id, name=name)
    session.add(timeline)
    session.commit()
    session.refresh(timeline)
    return _timeline_to_read(session, timeline)


def list_timelines(session: Session, project_id: str) -> list[TimelineRead]:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    timelines = session.exec(
        select(Timeline)
        .where(Timeline.project_id == project_id)
        .order_by(Timeline.created_at)  # type: ignore[arg-type]
    ).all()
    return [_timeline_to_read(session, t) for t in timelines]


def get_timeline(session: Session, timeline_id: str) -> TimelineRead:
    timeline = session.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    return _timeline_to_read(session, timeline)


# ---------------------------------------------------------------------------
# Timeline items
# ---------------------------------------------------------------------------

def _ordered_items(session: Session, timeline_id: str) -> list[TimelineItem]:
    return list(
        session.exec(
            select(TimelineItem)
            .where(TimelineItem.timeline_id == timeline_id)
            .order_by(TimelineItem.position)  # type: ignore[arg-type]
        ).all()
    )


def _renumber(session: Session, items: list[TimelineItem]) -> None:
    for i, item in enumerate(items):
        if item.position != i:
            item.position = i
            session.add(item)


def add_item(
    session: Session, timeline_id: str, data: TimelineItemCreate
) -> TimelineRead:
    timeline = session.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    clip = session.get(Clip, data.clip_id)
    if clip is None or clip.project_id != timeline.project_id:
        raise HTTPException(status_code=404, detail="Clip not found in this project")

    items = _ordered_items(session, timeline_id)
    session.add(
        TimelineItem(timeline_id=timeline_id, clip_id=data.clip_id, position=len(items))
    )
    session.commit()
    return _timeline_to_read(session, timeline)


def move_item(
    session: Session, timeline_id: str, item_id: str, data: TimelineItemMove
) -> TimelineRead:
    timeline = session.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    items = _ordered_items(session, timeline_id)
    target = next((i for i in items if i.id == item_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Timeline item not found")

    items.remove(target)
    items.insert(min(data.position, len(items)), target)
    _renumber(session, items)
    session.commit()
    return _timeline_to_read(session, timeline)


def remove_item(session: Session, timeline_id: str, item_id: str) -> None:
    timeline = session.get(Timeline, timeline_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="Timeline not found")
    item = session.get(TimelineItem, item_id)
    if item is None or item.timeline_id != timeline_id:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    session.delete(item)
    remaining = [i for i in _ordered_items(session, timeline_id) if i.id != item_id]
    _renumber(session, remaining)
    session.commit()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_timeline(session: Session, timeline_id: str, fmt: str) -> tuple[str, str, str]:
    """
    Return (content, media_type, filename) for a timeline export.

    JSON is the full structure; CSV is one row per ordered item — both carry
    everything an editor needs to rebuild the cut (source file, in/out points).
    """
    timeline = get_timeline(session, timeline_id)

    if fmt == "json":
        content = timeline.model_dump_json(indent=2)
        return content, "application/json", f"timeline_{timeline_id[:8]}.json"

    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["position", "asset_filename", "asset_id", "start_s", "end_s",
             "duration_s", "label"]
        )
        for item in timeline.items:
            c = item.clip
            writer.writerow(
                [item.position, c.asset_filename, c.asset_id, c.start, c.end,
                 round(c.end - c.start, 3), c.label]
            )
        return buf.getvalue(), "text/csv", f"timeline_{timeline_id[:8]}.csv"

    raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'")
