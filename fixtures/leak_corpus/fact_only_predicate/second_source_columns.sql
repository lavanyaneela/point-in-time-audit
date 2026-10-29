SELECT p.entity_id, MAX(i.severity) AS worst
FROM predictions AS p
JOIN incidents AS i
  ON i.entity_id = p.entity_id
 AND i.occurred_at <= p.prediction_time
GROUP BY p.entity_id
