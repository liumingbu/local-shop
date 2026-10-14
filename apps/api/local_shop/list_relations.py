"""Request-local page prefetch, preserving existing DTO/privacy filters without N+1 SQL."""

from sqlalchemy import select, tuple_

from .models import CancellationRequest, ConfirmationRevision, MediaObject, PrivateAttachment


def prefetch(session, records):
    keys = [(row.tenant_id, row.id) for row in records]
    cache = {key: {"cancellations": [], "revisions": [], "attachments": []} for key in keys}
    session.info["reservation_page_relations"] = cache
    if not keys:
        return
    for model, name, ordering in [
        (CancellationRequest, "cancellations", CancellationRequest.requested_version),
        (ConfirmationRevision, "revisions", ConfirmationRevision.proposed_version),
    ]:
        for row in session.scalars(
            select(model)
            .where(tuple_(model.tenant_id, model.reservation_id).in_(keys))
            .order_by(ordering)
        ):
            cache[(row.tenant_id, row.reservation_id)][name].append(row)
    query = (
        select(MediaObject, PrivateAttachment)
        .join(
            PrivateAttachment,
            (MediaObject.id == PrivateAttachment.media_id)
            & (MediaObject.tenant_id == PrivateAttachment.tenant_id),
        )
        .where(
            tuple_(PrivateAttachment.tenant_id, PrivateAttachment.reservation_id).in_(keys),
            MediaObject.purpose == "PRIVATE",
            MediaObject.status == "ACTIVE",
        )
        .order_by(PrivateAttachment.sort_order, PrivateAttachment.id)
    )
    for media, attachment in session.execute(query):
        cache[(attachment.tenant_id, attachment.reservation_id)]["attachments"].append(
            (media, attachment)
        )


def cached(session, tenant, record, name):
    value = session.info.get("reservation_page_relations", {}).get((tenant, record))
    return value[name] if value is not None else None
