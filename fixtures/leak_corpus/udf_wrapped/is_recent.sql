-- The predicate exists, inside a function nobody can statically read.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE is_recent(e.arrival_time)
  AND e.fact_time <= p.prediction_time
GROUP BY p.entity_id
