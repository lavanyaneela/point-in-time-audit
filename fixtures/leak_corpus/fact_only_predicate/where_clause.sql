SELECT p.entity_id, MAX(e.value) AS worst
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE e.fact_time <= p.prediction_time
GROUP BY p.entity_id
