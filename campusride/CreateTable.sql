Drop TABLE IF EXISTS report CASCADE;
DROP TABLE IF EXISTS Ride CASCADE;
DROP TABLE IF EXISTS Offer CASCADE;
DROP TABLE IF EXISTS Post CASCADE;
DROP TABLE IF EXISTS Car CASCADE;
DROP TABLE IF EXISTS Driver CASCADE;
DROP TABLE IF EXISTS Passenger CASCADE;
DROP TABLE IF EXISTS AdminPermission CASCADE;
DROP TABLE IF EXISTS Admin CASCADE;
DROP TABLE IF EXISTS "User" CASCADE;

CREATE TABLE "User" (
    user_ID SERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    user_name VARCHAR(50) NOT NULL UNIQUE,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    surname VARCHAR(50) NOT NULL,
    gender VARCHAR(20) NOT NULL
);

CREATE TABLE Admin (
    user_ID INT PRIMARY KEY,
    FOREIGN KEY (user_ID) REFERENCES "User"(user_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE AdminPermission (
    user_ID INT NOT NULL,
    permission VARCHAR(50) NOT NULL,
    PRIMARY KEY (user_ID, permission),
    FOREIGN KEY (user_ID) REFERENCES Admin(user_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE Passenger (
    user_ID INT PRIMARY KEY,
    FOREIGN KEY (user_ID) REFERENCES "User"(user_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE Driver (
    user_ID INT PRIMARY KEY,
    rate NUMERIC(3,2) DEFAULT 0.00,
    CHECK (rate >= 0 AND rate <= 5),
    FOREIGN KEY (user_ID) REFERENCES "User"(user_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE Car (
    plate_number VARCHAR(20) PRIMARY KEY,
    brand VARCHAR(50) NOT NULL,
    model VARCHAR(50) NOT NULL,
    seat_number INT NOT NULL,
    driver_ID INT NOT NULL,
    CHECK (seat_number > 0),
    FOREIGN KEY (driver_ID) REFERENCES Driver(user_ID)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE Post (
    post_ID VARCHAR(20) PRIMARY KEY,
    passenger_number INT NOT NULL,
    location VARCHAR(100) NOT NULL,
    date_time TIMESTAMP NOT NULL,
    passenger_ID INT NOT NULL,
    CHECK (passenger_number > 0),
    FOREIGN KEY (passenger_ID) REFERENCES Passenger(user_ID)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE Offer (
    offer_ID VARCHAR(20) PRIMARY KEY,
    post_ID VARCHAR(20) NOT NULL,
    driver_ID INT NOT NULL,
    FOREIGN KEY (post_ID) REFERENCES Post(post_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    FOREIGN KEY (driver_ID) REFERENCES Driver(user_ID)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE Ride (
    ride_ID VARCHAR(20) PRIMARY KEY,
    start_destination VARCHAR(100) NOT NULL,
    end_destination VARCHAR(100) NOT NULL,
    cost NUMERIC(10,2) NOT NULL,
    rating INT,
    offer_ID VARCHAR(20) NOT NULL UNIQUE,
    plate_number VARCHAR(20) NOT NULL,
    CHECK (cost >= 0),
    CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5)),
    FOREIGN KEY (offer_ID) REFERENCES Offer(offer_ID)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    FOREIGN KEY (plate_number) REFERENCES Car(plate_number)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE report (
    ride_ID VARCHAR(20) NOT NULL,
    user_ID INT NOT NULL,
    PRIMARY KEY (ride_ID, user_ID),
    FOREIGN KEY (ride_ID) REFERENCES Ride(ride_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE,
    FOREIGN KEY (user_ID) REFERENCES Passenger(user_ID)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);