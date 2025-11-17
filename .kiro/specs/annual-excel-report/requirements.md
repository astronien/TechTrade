# Requirements Document

## Introduction

This document specifies requirements for an Annual Trade Report feature that generates Excel files with monthly trade statistics and charts, delivered via LINE Bot. The feature allows users to request yearly trade reports by sending a keyword command through LINE, and receive a formatted Excel file containing trade counts per month with visual charts.

## Glossary

- **System**: The Annual Trade Report Generator
- **LINE Bot**: The messaging interface that receives commands and sends Excel files
- **Trade Record**: A single trade-in transaction retrieved from the external API
- **Excel Report**: An Excel file containing monthly trade statistics and charts
- **User**: A person interacting with the LINE Bot
- **Branch**: A store location identified by branch_id
- **API**: The external eve.techswop.com API that provides trade data
- **document_date**: The date field in trade records (format: DD/MM/YYYY)

## Requirements

### Requirement 1

**User Story:** As a user, I want to request an annual trade report via LINE Bot, so that I can receive trade statistics for a specific year

#### Acceptance Criteria

1. WHEN THE User sends "รายงาน excel รายปี" to THE LINE Bot, THE System SHALL generate an Excel report for the current year
2. WHEN THE User sends "รายงาน excel รายปี [YYYY]" to THE LINE Bot, THE System SHALL generate an Excel report for the specified year
3. WHEN THE User sends "รายงาน excel รายปี [branch_id]" to THE LINE Bot, THE System SHALL generate an Excel report for the current year filtered by the specified branch
4. WHEN THE User sends "รายงาน excel รายปี [YYYY] [branch_id]" to THE LINE Bot, THE System SHALL generate an Excel report for the specified year filtered by the specified branch
5. WHEN THE System receives a valid report request, THE System SHALL respond within 60 seconds

### Requirement 2

**User Story:** As a user, I want the Excel report to contain monthly trade counts, so that I can analyze trade volume trends throughout the year

#### Acceptance Criteria

1. THE Excel Report SHALL contain a table with 12 columns representing months (JAN through DEC)
2. THE Excel Report SHALL contain rows showing trade counts for each month
3. WHEN THE System processes trade records, THE System SHALL group trades by month based on the document_date field
4. THE Excel Report SHALL display numeric values for trade counts in each month cell
5. WHEN no trades exist for a specific month, THE System SHALL display zero in that month's cell

### Requirement 3

**User Story:** As a user, I want the Excel report to include visual charts, so that I can quickly understand trade patterns

#### Acceptance Criteria

1. THE Excel Report SHALL contain a line chart displaying monthly trade counts
2. THE Excel Report SHALL contain a bar chart displaying monthly trade counts
3. WHEN THE System generates charts, THE System SHALL use month names as x-axis labels
4. WHEN THE System generates charts, THE System SHALL use trade counts as y-axis values
5. THE Line Chart SHALL display data points connected by lines showing trade volume trends

### Requirement 4

**User Story:** As a user, I want to receive the Excel file through LINE Bot, so that I can download and view it on my device

#### Acceptance Criteria

1. WHEN THE System completes report generation, THE System SHALL send the Excel file to THE User via LINE Bot
2. THE Excel File SHALL have a descriptive filename including the year and branch information
3. WHEN THE System encounters an error during generation, THE System SHALL send an error message to THE User
4. THE Excel File SHALL be in .xlsx format compatible with Microsoft Excel and Google Sheets
5. WHEN THE System sends the file, THE System SHALL include a text message describing the report contents

### Requirement 5

**User Story:** As a system administrator, I want the system to fetch trade data from the external API, so that reports contain accurate and up-to-date information

#### Acceptance Criteria

1. WHEN THE System generates a report, THE System SHALL fetch trade data from the eve.techswop.com API
2. THE System SHALL retrieve all trade records for the specified year using date range filters
3. WHEN fetching data for a full year, THE System SHALL handle pagination to retrieve all records
4. THE System SHALL parse the document_date field to determine which month each trade belongs to
5. WHEN THE API returns an error, THE System SHALL notify THE User with a descriptive error message

### Requirement 6

**User Story:** As a user, I want the system to handle different year formats, so that I can request reports flexibly

#### Acceptance Criteria

1. WHEN THE User specifies a year in Buddhist Era format (e.g., 2567), THE System SHALL convert it to Gregorian calendar year
2. WHEN THE User specifies a year in Gregorian format (e.g., 2024), THE System SHALL use it directly
3. THE System SHALL accept years between 2020 and the current year plus one
4. WHEN THE User specifies an invalid year, THE System SHALL send an error message explaining valid year ranges
5. WHEN no year is specified, THE System SHALL default to the current year

### Requirement 7

**User Story:** As a user, I want the Excel report to be properly formatted, so that it is easy to read and professional-looking

#### Acceptance Criteria

1. THE Excel Report SHALL have a header row with month abbreviations (JAN, FEB, MAR, etc.)
2. THE Excel Report SHALL use a clear font with appropriate sizing for readability
3. THE Excel Report SHALL apply cell borders to the data table
4. THE Excel Report SHALL use column widths that accommodate the data without truncation
5. THE Excel Report SHALL position charts below the data table with appropriate spacing

### Requirement 8

**User Story:** As a developer, I want the system to handle concurrent requests, so that multiple users can request reports simultaneously

#### Acceptance Criteria

1. WHEN multiple users send report requests simultaneously, THE System SHALL process each request independently
2. THE System SHALL not mix data between different user requests
3. WHEN THE System processes a request, THE System SHALL use a unique identifier for temporary files
4. THE System SHALL clean up temporary files after sending them to users
5. THE System SHALL handle at least 5 concurrent report generation requests

### Requirement 9

**User Story:** As a user, I want to see a progress indicator, so that I know the system is working on my request

#### Acceptance Criteria

1. WHEN THE System receives a report request, THE System SHALL immediately send an acknowledgment message
2. THE Acknowledgment Message SHALL indicate that report generation is in progress
3. THE Acknowledgment Message SHALL include an estimated completion time
4. WHEN report generation takes longer than 30 seconds, THE System SHALL send a status update message
5. WHEN THE System completes the report, THE System SHALL send a completion message before sending the file

### Requirement 10

**User Story:** As a user, I want the system to validate my input, so that I receive helpful feedback for incorrect commands

#### Acceptance Criteria

1. WHEN THE User sends an invalid command format, THE System SHALL respond with usage examples
2. WHEN THE User specifies an invalid branch_id, THE System SHALL respond with an error message listing valid branch IDs
3. WHEN THE User specifies an invalid year, THE System SHALL respond with an error message explaining the valid year range
4. THE Error Messages SHALL be in Thai language for user clarity
5. THE Error Messages SHALL include correct command format examples
