SELECT p.entity_id, COUNT(e.value) AS n_events, COUNT(i.severity) AS n_incidents
FROM predictions AS p
JOIN events AS e
  ON e.entity_id = p.entity_id
 AND e.fact_time <= p.prediction_time
 AND e.arrival_time <= p.prediction_time
JOIN incidents AS i
  ON i.entity_id = p.entity_id
 AND i.occurred_at <= p.prediction_time
 AND i.recorded_at <= p.prediction_time
GROUP BY p.entity_id
