# Automated-Helpdesk-Reasoner
# Automated Helpdesk Reasoner

## Project Overview

Automated Helpdesk Reasoner is a Python-based web application developed using Flask and SQLite. The system helps users submit support requests, automatically categorizes issues, suggests solutions based on predefined rules, and generates support tickets for unresolved problems.

## Features

* User-friendly web interface
* Automated issue classification
* Rule-based reasoning engine
* Ticket generation with unique IDs
* Priority assignment (Low, Medium, High)
* SQLite database integration
* Ticket status tracking
* Admin dashboard for ticket management

## Technology Stack

* Python
* Flask
* SQLite
* HTML
* CSS
* JavaScript

## Project Structure

helpdesk/
│
├── app.py
├── helpdesk.db
├── requirements.txt
├── README.md
│
├── templates/
│ ├── index.html
│ ├── tickets.html
│ └── admin.html
│
└── static/
├── css/
└── js/

## Installation

1. Clone or download the project.
2. Create a virtual environment:

```bash
python -m venv .venv
```

3. Activate the virtual environment:

Windows:

```bash
.venv\Scripts\activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

5. Run the application:

```bash
python app.py
```

6. Open your browser and visit:

```text
http://127.0.0.1:5000
```

## How It Works

1. User submits an issue.
2. System analyzes keywords.
3. Issue category is identified.
4. Suggested solution is displayed.
5. Ticket is generated and stored in the database.
6. Admin can monitor and update ticket status.

## Example Categories

* Login Issues
* Network Problems
* Software Errors
* Hardware Issues
* Other Support Requests

## Future Enhancements

* AI-powered chatbot
* Email notifications
* Machine learning-based classification
* Voice-based complaint registration
* Analytics dashboard

## Author

Developed as a CFAI / B.Tech Academic Project for demonstrating Python, Flask, Database Management, and Intelligent Helpdesk Automation concepts.

