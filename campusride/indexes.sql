-- PostgreSQL Indexes for CampusRide Workload

-- Index for finding posts created by a specific passenger.
CREATE INDEX IF NOT EXISTS idx_post_passenger_id
ON Post(passenger_ID);

-- Index for finding posts according to date and time.
CREATE INDEX IF NOT EXISTS idx_post_date_time
ON Post(date_time);

-- Index for listing offers received by a specific post.
CREATE INDEX IF NOT EXISTS idx_offer_post_id
ON Offer(post_ID);

-- Index for listing offers made by a specific driver.
CREATE INDEX IF NOT EXISTS idx_offer_driver_id
ON Offer(driver_ID);

-- Unique index to prevent the same driver from making more than one offer for the same post.
CREATE UNIQUE INDEX IF NOT EXISTS idx_offer_post_driver_unique
ON Offer(post_ID, driver_ID);

-- Index for filtering rides according to cost.
CREATE INDEX IF NOT EXISTS idx_ride_cost
ON Ride(cost);

-- Index for filtering rides according to rating.
CREATE INDEX IF NOT EXISTS idx_ride_rating
ON Ride(rating);

-- Composite index for update and filtering operations using both cost and rating.
CREATE INDEX IF NOT EXISTS idx_ride_cost_rating
ON Ride(cost, rating);

-- Index for finding cars owned by a specific driver.
CREATE INDEX IF NOT EXISTS idx_car_driver_id
ON Car(driver_ID);

-- Index for finding reports submitted by a specific user.
CREATE INDEX IF NOT EXISTS idx_report_user_id
ON Report(user_ID);

-- Index for searching users by name and surname.
CREATE INDEX IF NOT EXISTS idx_user_name_surname
ON "User"(name, surname);