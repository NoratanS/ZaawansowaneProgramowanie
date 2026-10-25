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

**Courier**:
The component that performs Delivery: takes finished Analysis Results off the queue and hands them to the Results Service, retrying through outages.
_Avoid_: Delivery worker, dispatcher, consumer (unqualified)

## Analysis

**Analysis Request**:
A client's ask to count the people in the image at a given URL.
_Avoid_: Submission, task

**Analysis Job**:
An accepted Analysis Request waiting in or moving through the queue. Identified by a job id that the Analysis Service assigns on acceptance and that stays with it through to its Analysis Result.
_Avoid_: Task, message (when the domain concept is meant)

**Analysis Result**:
The outcome of one Analysis Job: either the person count in its image, or the reason the image could not be counted.
_Avoid_: Output, prediction

**Delivery**:
Handing an Analysis Result to the Results Service; must survive temporary outages of the Results Service or the edge proxy in front of it.
_Avoid_: Callback, push
