-- E2.a ground truth: catalog rows with Beatport-sourced bpm AND key (authority
-- for shared-catalog bpm/key, Data Authority Principle #3) AND a fetchable
-- Deezer 30s preview. This is the frozen benchmark sample (persist the CSV).
COPY (
  SELECT id, artist, title, bpm, key, deezer_id
  FROM catalog
  WHERE bpm_source = 'beatport'
    AND key_source = 'beatport'
    AND bpm IS NOT NULL
    AND key IS NOT NULL
    AND has_preview = true
    AND deezer_id IS NOT NULL
    AND deezer_id <> 'NOT_FOUND'
  ORDER BY random()
  LIMIT 600
) TO STDOUT WITH (FORMAT csv, HEADER true);
