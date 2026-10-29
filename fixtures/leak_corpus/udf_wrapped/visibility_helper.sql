SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE knowable_at(e.arrival_time, e.fact_time, p.prediction_time)
GROUP BY p.entity_id
