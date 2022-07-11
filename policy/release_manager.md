# Release manager role

## Appointment

A release manager (RM) is appointed for a specific upcoming release.

A RM may and should step down at any time, when they cannot fulfill the associated obligations. In this case, a new RM is appointed.

The appointment of an RM ends with the declaration of the respective release's end-of-life by the RM.

## Responsibilities

Immediately after the previous release was made, the RM takes over decision making regarding merges into the integration branch for all developments targeting the respective release. Such merges can be made as soon as, but no earlier than, the RM indicates approval.

It is the RM's responsibility to act on any merge request in a timely manner.

An RM is not expected to be an expert in all techniques, features, and parts of the code base. Consequently, an RM should seek feedback prior to approving merge requests whenever necessary.

The RM declares the time of a feature freeze for the upcoming release.

The RM decides on the length of the consolidation period following a feature freeze, and decides which kinds of changes are still acceptable.

The RM decides on the number and timing of potential release candidates, and on the timing of the final release.

After the initial release, the RM takes over the decision making for the respective maintenance branch in the same fashion as for the prior development towards the initial release. The RM decides on the nature of changes qualified for maintenance releases, and their timing.


## Assistant release manager role

In addition to an RM there is an assistant RM to prevent disruption in cases where the RM temporarily cannot act on their duties.

The assistant RM role is identical to the RM, with the same responsibilities. 


## Transition of release manager appointments

The assistant RM (aRM) becomes the RM when the current RM completed a release cycle and took over the new maintenance series. 

The aRM becomes the RM when the current RM steps down prior to completion of the release cycle.

The RM of an upcoming release serves as the aRM of the current maintenance series.

An aRM for the upcoming release is appointed by the project at the start of a release cycle.

Consequently, there is an RM and aRM for any given release series. A RM will therefore typically transition through the following stages

- appointment as aRM for the upcoming release (R+1)
- appointment as RM for release R+2 and continuing to be the aRM for the release R+1
- RM for the maintenance phase of release R+2 until its end-of-life
