-- C9.0 ground truth: DJ-set CO-OCCURRENCE among previewable tracks.
--
-- The benchmark question (roadmap C9.a bullet 3): do content-embedding neighbours
-- predict co-occurrence in DJ sets? Two tracks "co-occur" if they appear in the
-- same reliable root set. We export a bounded, CO-OCCURRENCE-DENSE universe by
-- sampling whole sets (not random tracks — random tracks almost never co-occur),
-- then exporting the (set_id, track) membership so the eval script can rebuild
-- both the universe and the co-occurrence graph.
--
-- Frozen sample: run once, persist sample.csv, reuse (ORDER BY random() is the
-- only non-determinism; the committed CSV is the ground truth).
--
-- Filters mirror the app: roots only (parent_set_id IS NULL), reliable only
-- (unreliable IS NOT TRUE, C8), and a fetchable Deezer preview (needed to embed).
WITH sampled_sets AS (
  SELECT s.id
  FROM sets s
  JOIN set_tracks st ON st.set_id = s.id
  JOIN catalog c ON c.id = st.catalog_id
  WHERE s.parent_set_id IS NULL
    AND s.unreliable IS NOT TRUE
    AND c.has_preview = true
    AND c.deezer_id IS NOT NULL
    AND c.deezer_id <> 'NOT_FOUND'
  GROUP BY s.id
  HAVING count(DISTINCT c.id) >= 8   -- enough previewable tracks to form real co-occurrence
  ORDER BY random()
  LIMIT 500
)
SELECT DISTINCT
  st.set_id,
  c.id AS catalog_id,
  c.deezer_id,
  c.artist,
  c.title
FROM sampled_sets ss
JOIN set_tracks st ON st.set_id = ss.id
JOIN catalog c ON c.id = st.catalog_id
WHERE c.has_preview = true
  AND c.deezer_id IS NOT NULL
  AND c.deezer_id <> 'NOT_FOUND'
ORDER BY st.set_id, c.id;
