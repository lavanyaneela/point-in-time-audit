-- Same join, 1992 spelling.
SELECT p.entity_id, MAX(e.value) AS worst
FROM predictions p, events e
WHERE e.entity_id = p.entity_id
GROUP BY p.entity_id
