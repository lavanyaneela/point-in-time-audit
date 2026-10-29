-- Semantically correct. The analyzer flags it anyway, and E3 prices that.
SELECT p.entity_id, COUNT(*) AS n
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
WHERE point_in_time_ok(e.fact_time, e.arrival_time, p.prediction_time)
GROUP BY p.entity_id
