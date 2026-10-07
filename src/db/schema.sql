-- HR Graph RAG - relational schema (PostgreSQL)
-- The COMMENT ON statements matter: the Text-to-SQL agent (Step 6) reads them
-- to understand what each table and column means.

DROP VIEW IF EXISTS v_employee_overview;
DROP TABLE IF EXISTS candidates, employee_trainings, trainings, payroll, attendance,
    performance_reviews, project_assignments, projects, employee_skills, skills,
    employees, departments CASCADE;

CREATE TABLE departments (
    dept_id      INT PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    location     TEXT NOT NULL,
    head_emp_id  INT                      -- FK added after employees are loaded
);

CREATE TABLE employees (
    emp_id           INT PRIMARY KEY,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    gender           TEXT CHECK (gender IN ('Male', 'Female', 'Other')),
    date_of_birth    DATE,
    hire_date        DATE NOT NULL,
    dept_id          INT NOT NULL REFERENCES departments(dept_id),
    designation      TEXT NOT NULL,
    level            SMALLINT NOT NULL CHECK (level BETWEEN 0 AND 3),
    manager_id       INT REFERENCES employees(emp_id),
    location         TEXT,
    employment_type  TEXT CHECK (employment_type IN ('Full-time', 'Contract', 'Intern')),
    status           TEXT CHECK (status IN ('Active', 'On Leave', 'Resigned')),
    experience_years SMALLINT CHECK (experience_years >= 0)
);

CREATE TABLE skills (
    skill_id  INT PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    category  TEXT NOT NULL
);

CREATE TABLE employee_skills (
    emp_id      INT REFERENCES employees(emp_id),
    skill_id    INT REFERENCES skills(skill_id),
    proficiency SMALLINT CHECK (proficiency BETWEEN 1 AND 5),
    years_used  SMALLINT,
    PRIMARY KEY (emp_id, skill_id)
);

CREATE TABLE projects (
    project_id  INT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    client      TEXT,
    dept_id     INT REFERENCES departments(dept_id),
    start_date  DATE,
    end_date    DATE,
    status      TEXT CHECK (status IN ('Completed', 'Ongoing', 'On Hold')),
    tech_stack  TEXT
);

CREATE TABLE project_assignments (
    emp_id          INT REFERENCES employees(emp_id),
    project_id      INT REFERENCES projects(project_id),
    role            TEXT,
    allocation_pct  SMALLINT CHECK (allocation_pct BETWEEN 0 AND 100),
    start_date      DATE,
    end_date        DATE,
    PRIMARY KEY (emp_id, project_id)
);

CREATE TABLE attendance (
    emp_id         INT REFERENCES employees(emp_id),
    month          CHAR(7),
    working_days   SMALLINT,
    days_present   SMALLINT,
    leaves_taken   SMALLINT,
    late_arrivals  SMALLINT,
    PRIMARY KEY (emp_id, month)
);

CREATE TABLE payroll (
    emp_id      INT REFERENCES employees(emp_id),
    month       CHAR(7),
    basic       INT,
    hra         INT,
    allowances  INT,
    deductions  INT,
    net_pay     INT,
    PRIMARY KEY (emp_id, month)
);

CREATE TABLE trainings (
    training_id     INT PRIMARY KEY,
    name            TEXT NOT NULL,
    skill_id        INT REFERENCES skills(skill_id),
    provider        TEXT,
    duration_hours  SMALLINT
);

CREATE TABLE employee_trainings (
    emp_id           INT REFERENCES employees(emp_id),
    training_id      INT REFERENCES trainings(training_id),
    completion_date  DATE,
    score            SMALLINT CHECK (score BETWEEN 0 AND 100),
    PRIMARY KEY (emp_id, training_id)
);

CREATE TABLE performance_reviews (
    review_id      INT PRIMARY KEY,
    emp_id         INT REFERENCES employees(emp_id),
    reviewer_id    INT REFERENCES employees(emp_id),
    review_period  TEXT NOT NULL,
    rating         NUMERIC(2,1) CHECK (rating BETWEEN 1 AND 5),
    goals_met_pct  SMALLINT,
    UNIQUE (emp_id, review_period)
);

CREATE TABLE candidates (
    candidate_id      INT PRIMARY KEY,
    name              TEXT NOT NULL,
    email             TEXT,
    applied_role      TEXT,
    experience_years  SMALLINT,
    status            TEXT CHECK (status IN ('Applied', 'Shortlisted', 'Interviewed', 'Rejected', 'Offered')),
    resume_file       TEXT
);

-- ---------------------------------------------------------------- indexes
CREATE INDEX idx_emp_dept      ON employees(dept_id);
CREATE INDEX idx_emp_manager   ON employees(manager_id);
CREATE INDEX idx_es_skill      ON employee_skills(skill_id);
CREATE INDEX idx_pa_project    ON project_assignments(project_id);
CREATE INDEX idx_pr_emp        ON performance_reviews(emp_id);

-- ---------------------------------------------------------------- descriptions (used by Text-to-SQL)
COMMENT ON TABLE departments IS 'Company departments with their office location and department head';
COMMENT ON TABLE employees IS 'One row per employee, including current designation, department and reporting manager';
COMMENT ON COLUMN employees.level IS '0 = junior, 1 = mid, 2 = senior, 3 = department manager';
COMMENT ON COLUMN employees.manager_id IS 'emp_id of the reporting manager (NULL for department heads)';
COMMENT ON COLUMN employees.status IS 'Active, On Leave or Resigned';
COMMENT ON TABLE skills IS 'Master list of technical and business skills';
COMMENT ON TABLE employee_skills IS 'Which employee has which skill';
COMMENT ON COLUMN employee_skills.proficiency IS '1 = beginner ... 5 = expert';
COMMENT ON TABLE projects IS 'Client and internal projects';
COMMENT ON COLUMN projects.tech_stack IS 'Semicolon-separated list of skills/technologies used';
COMMENT ON TABLE project_assignments IS 'Which employee worked on which project and in what role';
COMMENT ON TABLE attendance IS 'Monthly attendance summary per employee; month format YYYY-MM';
COMMENT ON TABLE payroll IS 'Monthly salary slip per employee in INR; month format YYYY-MM';
COMMENT ON TABLE trainings IS 'Training courses, each linked to the skill it teaches';
COMMENT ON TABLE employee_trainings IS 'Trainings completed by employees with their score out of 100';
COMMENT ON TABLE performance_reviews IS 'Half-yearly performance ratings (1-5); review_period is like 2025-H1 or 2025-H2';
COMMENT ON TABLE candidates IS 'Job applicants; resume_file is the matching resume document';

-- ---------------------------------------------------------------- convenience view
CREATE VIEW v_employee_overview AS
SELECT e.emp_id,
       e.first_name || ' ' || e.last_name            AS employee_name,
       e.designation,
       d.name                                        AS department,
       e.location,
       e.status,
       e.experience_years,
       m.first_name || ' ' || m.last_name            AS manager_name,
       (SELECT pr.rating FROM performance_reviews pr
         WHERE pr.emp_id = e.emp_id ORDER BY pr.review_period DESC LIMIT 1) AS latest_rating,
       (SELECT ROUND(100.0 * SUM(a.days_present) / NULLIF(SUM(a.working_days), 0), 1)
          FROM attendance a WHERE a.emp_id = e.emp_id)                     AS attendance_pct
FROM employees e
JOIN departments d ON d.dept_id = e.dept_id
LEFT JOIN employees m ON m.emp_id = e.manager_id;
COMMENT ON VIEW v_employee_overview IS 'One-row summary per employee: department, manager, latest rating and overall attendance %';
