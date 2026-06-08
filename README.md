# CampusRide: Smart Campus Transportation Network

CampusRide is a comprehensive web application designed to optimize intra-campus commute efficiency for university networks. Developed as a full-stack engineering solution, the platform bridges 'Passengers' requesting rides with certified 'Drivers', enforced by relational database constraints, dynamic attribute updates, and secure cryptographic handshakes.

## Architectural Core & Relational Database Design
The foundation of CampusRide relies heavily on the **Enhanced Entity-Relationship (EER)** model, emphasizing strict data integrity and real-world campus commute semantics.

## Advanced EER Modeling & Constraints
* **Overlap Specialization (O):** Modeled using the Overlap constraint from the `User` supertype down to `Admin`, `Passenger`, and `Driver` subtypes. This allows structural flexibility, enabling an Admin to simultaneously act as a Passenger to request rides, or a Driver to switch roles seamlessly without compromising relational mapping.
* **Referential Integrity Constraints:** Robust `FOREIGN KEY` constraints (e.g., `ON DELETE CASCADE`) manage the relational cascade between tuples in `Post`, `Offer`, and `Ride` relations, preventing orphaned records.
* **Business Logic Constraints:** Sourced directly from local PostgreSQL schemas, the platform enforces capacity validation logic ensuring that a driver's vehicle passenger capacity (`Car.seat_number`) strictly satisfies the passenger request constraint (`Post.passenger_number`).
* **Optimized Cost Normalization:** To model real-world bidding negotiations, the `cost` attribute is normalized inside the `Offer` relation rather than the final `Ride` schema, enabling dynamic proposal evaluations before ride initialization.

## Tech Stack & System Components

* **Backend Engine:** Python 3 with **Flask** (Micro-framework architecture)
* **Database Management System:** **PostgreSQL** (Relational instance)
* **Database Driver:** `pg8000` (Pure-Python database interface)
* **Frontend UI:** Semantically structured **HTML5**, **CSS3 (Custom Flexbox/Grid)**, and asynchronous **JavaScript (Fetch API)** mirroring premium SaaS application matrices.
* **Security Layer:** Cryptographic password hashing powered by `werkzeug.security` via salted **Scrypt** algorithms to protect sensitive user credentials against reverse-engineering vectors.

## Key System Features

1. **Dynamic Authentication Matrix:** Dual-layer login mechanics that automatically determine roles (Admin vs. Standard User Matrix). Includes a simulated OTP Security Gateway for transaction verification.
2. **The Active Posts Feed:** Case-insensitive, real-time filtered lookup engine utilizing SQL `LOWER()` and pattern matching (`LIKE %search%`) to fetch live commuter requests instantly.
3. **Interactive Offer Bidding:** Passengers can audit multiple incoming bids from distinct drivers, complete with live Driver Ratings, Car Attribute Lookups, and Proposed Costs before selecting `Accept` or `Reject`.
4. **Automated Ride Provisioning:** Accepting a driver's proposal automatically triggers an atomic transaction fanning out to instantiate a new record in the `Ride` tuple matrix.
5. **Dynamic Database Mutator (My Account):** A dedicated profile panel allowing active users to update telephone strings, gender attributes, and security credentials directly inside the local database instance using live `UPDATE` pipelines.
6. **Relational Analytical Rating (0-5 Stars):** Post-ride feedback updates the specific `Ride` record and executes a nested subquery to recalculate and store the overall cumulative average score (`Driver.rate`) dynamically.

        host="localhost",
        port=5432
    )
