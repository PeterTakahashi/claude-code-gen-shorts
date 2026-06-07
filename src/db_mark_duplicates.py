"""One-off helper to record the elonmusk duplicate uploads in the DB.

These were created accidentally by running `youtube_batch_upload --force` after
the first batch partially failed. Each old video_id is marked as superseded
by the current canonical one. The user should delete the old ones via YouTube
Studio (the DB can't delete remote videos).

Run once. Idempotent.
"""
from __future__ import annotations

from .db import connect, upsert_video, mark_superseded

# (old_video_id, new_video_id, chapter_id)
DUPES = [
    ("lDcyJMAQPzk", "QU9qaJKGDb8", "main"),
    ("AjmDci4TRRs", "d-zqsELVMvY", "ch2"),
    ("iKajLolbZ0E", "kI2ggltL8vs", "ch3"),
    ("-yKrtwAyRuY", "KxpeeNjx5Jo", "ch4"),
    ("Jp5LYbIQtpQ", "htT6OJrn8J0", "ch5"),
    ("rYuWLw8mRs0", "O5KbfzHSBLo", "ch7"),
    ("7Y_FBGPahP0", "68yFn04aJ4c", "ch10"),
    ("cC2OmjbfYZA", "2iUKukhHlm4", "ch11"),
]


def main() -> int:
    with connect() as conn:
        # Look up titles for the canonical rows so we can copy them onto the old ones.
        for old_vid, new_vid, ch_id in DUPES:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT title, description, tags, master_mp4_path, thumbnail_path FROM videos WHERE video_id = %s",
                    (new_vid,),
                )
                row = cur.fetchone()
            if not row:
                print(f"  WARN: canonical {new_vid} not found in DB, skipping {old_vid}")
                continue
            title, desc, tags, mp4, thumb = row
            upsert_video(
                conn,
                video_id=old_vid,
                series_id="elonmusk",
                chapter_id=ch_id,
                kind="long",
                title=title + " (旧版・要削除)",
                description=desc,
                tags=tags,
                privacy="private",
                master_mp4_path=mp4,
                thumbnail_path=thumb,
                metadata={"note": "duplicate from first batch attempt; should be deleted via YouTube Studio"},
            )
            mark_superseded(conn, old_video_id=old_vid, new_video_id=new_vid)
            print(f"  marked {old_vid} → superseded by {new_vid}  ({ch_id})")
        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
