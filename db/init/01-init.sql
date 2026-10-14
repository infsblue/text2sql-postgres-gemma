-- Sample e-commerce schema, loaded on first database initialization.
CREATE TABLE customers (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    email      TEXT NOT NULL UNIQUE,
    country    TEXT NOT NULL,
    created_at DATE NOT NULL
);

CREATE TABLE products (
    id       SERIAL PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT NOT NULL,
    price    NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
    id          SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id),
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled'))
);

CREATE TABLE order_items (
    id         SERIAL PRIMARY KEY,
    order_id   INT NOT NULL REFERENCES orders(id),
    product_id INT NOT NULL REFERENCES products(id),
    quantity   INT NOT NULL CHECK (quantity > 0)
);

INSERT INTO customers (name, email, country, created_at) VALUES
    ('Ana Silva',   'ana@example.com',   'Brazil',  '2025-01-10'),
    ('John Smith',  'john@example.com',  'USA',     '2025-02-14'),
    ('Marie Curie', 'marie@example.com', 'France',  '2025-03-02'),
    ('Luis Perez',  'luis@example.com',  'Spain',   '2025-04-21'),
    ('Mei Tanaka',  'mei@example.com',   'Japan',   '2025-05-30');

INSERT INTO products (name, category, price) VALUES
    ('Laptop',     'Electronics', 1200.00),
    ('Headphones', 'Electronics',  150.00),
    ('Desk',       'Furniture',    300.00),
    ('Chair',      'Furniture',    180.00),
    ('Notebook',   'Stationery',     5.50);

INSERT INTO orders (customer_id, order_date, status) VALUES
    (1, '2025-06-01', 'delivered'),
    (1, '2025-07-15', 'shipped'),
    (2, '2025-06-20', 'delivered'),
    (3, '2025-08-05', 'pending'),
    (4, '2025-08-18', 'cancelled'),
    (5, '2025-09-02', 'delivered');

INSERT INTO order_items (order_id, product_id, quantity) VALUES
    (1, 1, 1), (1, 2, 2),
    (2, 5, 10),
    (3, 3, 1), (3, 4, 2),
    (4, 2, 1),
    (5, 1, 1),
    (6, 4, 1), (6, 5, 5);
