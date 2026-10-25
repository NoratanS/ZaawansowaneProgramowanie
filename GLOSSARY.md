# People Counter

Two microservices that count people in images submitted by URL and store the results, connected through a message broker.

## Services

**Analysis Service**:
The API that accepts Analysis Requests and enqueues them as Analysis Jobs. "Service B" in the assignment brief.
_Avoid_: Service B, AI service, detector API

**Worker**:
The consumer that takes an Analysis Job, counts the people in its image and produces an Analysis Result. Scaled horizontally via replicas.
_Avoid_: Consumer (unqualified), processor

**Results Service**:
The API that stores Analysis Results and serves them back. "Service A" in the assignment brief.
_Avoid_: Service A, database service

## Analysis

**Analysis Request**:
A client's ask to count the people in the image at a given URL.
_Avoid_: Submission, task

**Analysis Job**:
An accepted Analysis Request waiting in or moving through the queue.
_Avoid_: Task, message (when the domain concept is meant)

**Analysis Result**:
The person count for one Analysis Job, plus the metadata needed to identify it.
_Avoid_: Output, prediction

**Delivery**:
Handing an Analysis Result to the Results Service; must survive temporary outages of the Results Service or the edge proxy in front of it.
_Avoid_: Callback, push
