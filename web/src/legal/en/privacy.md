# Privacy Notice

Version {privacy_version}, effective {privacy_date}. Draft pending legal review.

This notice explains what personal data {app_name} processes, why, on what legal basis, for how long, and what your rights are. It is written for the people who use the Service (surgeons, trainees, researchers, administrators). Patient data contained in uploaded videos is covered in section 6.

## 1. Who is responsible

The data controller for your account data is {controller_name}, contact {controller_email}. For patient data inside videos, the uploading surgeon or their institution is the controller and we are the processor (section 6).

## 2. What we process about you

| Data | Source | Why |
| --- | --- | --- |
| Email address, password hash, two-factor secret, sign-in events | You, at sign-up and sign-in | To run your account and keep it secure |
| Name, title, specialty, language | You, in Settings | To show who you are to the people you share with |
| Team and institution memberships and roles | You or your administrators | To apply the permission rules |
| Videos you upload, their titles, procedure, operation date, and the analysis outputs | You and our processing | To provide the Service |
| Comments, quiz answers, annotations, progress | You | For the learning features |
| Feedback you send | You | To improve the Service |
| Usage events (pages visited, features used, time spent) and technical logs (IP address, browser, errors) | Automatic | To keep the Service working, secure, and to understand how it is used |
| Audit log of who viewed, shared, exported or deleted what | Automatic | Security and accountability, required for health data |

We do not use third-party advertising or analytics services. Usage measurement is done in our own database in the European Union.

## 3. Legal bases

- Running your account and providing the Service: performance of a contract (Article 6(1)(b) GDPR).
- Security, audit logging, usage measurement, fraud prevention: our legitimate interest in a secure and reliable Service (Article 6(1)(f)), balanced against your interests; you can object (section 8).
- Legal obligations, for example keeping records required by law: Article 6(1)(c).
- Anything optional, such as reuse of anonymised material for research or model training: your consent (Article 6(1)(a)), asked separately and revocable at any time. Nothing is reused without it.

## 4. Where data is kept and who helps us

All data is stored and processed in the European Union. We use these sub-processors under written agreements; the current list is published on the Sub-processors page:

- a managed PostgreSQL database and authentication service (EU region) for account data, metadata and analysis results;
- an object storage provider (EU region) for videos, streaming renditions and reports;
- a GPU computing provider (EU region) that runs the analysis models on your videos while an analysis is in progress;
- a hosting provider (EU region) for the application;
- a transactional email provider for sign-in links and notifications;
- an error monitoring service that receives technical error reports without video content.

We do not transfer personal data outside the EU/EEA. If that ever changes, we will update this notice and rely on an adequacy decision or standard contractual clauses.

## 5. How long we keep data

- Account data: for as long as your account exists, then deleted within 30 days of your deletion request (backups included).
- Original uploaded video files: 90 days after a successful analysis by default, then deleted; streaming renditions and analysis results stay for as long as the video is in your library. Institutions can set a different retention policy.
- Audit log and security logs: 12 months.
- Usage events: 24 months, then aggregated.
- Feedback: until resolved, at most 24 months.

## 6. Patient data inside videos

Operation videos are health data. They are uploaded by you or your institution under your own legal basis (for example consent obtained for recording and educational use, or an institutional research approval). You confirm this at every upload.

We minimise what we process: container metadata is stripped, frames showing the outside of the body are blurred, no patient identifiers are stored anywhere in our systems, and automated analysis works only on the endoscopic images. We never use patient video to train models without a separate, explicit opt-in from the controller.

Access to a video is limited to its owner and the people it is explicitly shared with; every view, share, export and deletion is written to the audit log. Playback uses short-lived, signed links; storage is encrypted at rest and in transit.

For institutions, a data processing agreement under Article 28 GDPR sets out our obligations as processor, including assistance with data subject requests, breach notification without undue delay, and deletion or return of data at the end of the agreement.

## 7. Cookies

See the Cookie Notice. We use only the cookies needed to keep you signed in and to remember your interface preferences.

## 8. Your rights

You can access, correct, download and delete your data, restrict or object to processing based on legitimate interest, withdraw consent for anything based on consent, and lodge a complaint with a supervisory authority (in Greece, the Hellenic Data Protection Authority, www.dpa.gr). Download and deletion are available in Settings; for anything else write to {controller_email}. We answer within one month.

If you are a patient whose operation video may have been uploaded by your surgeon or hospital, please contact that surgeon or hospital first: they are the controller and can act on your request; we will assist them.

## 9. Security

Row-level access rules in the database, encryption in transit and at rest, two-factor authentication, short-lived signed links for video, least-privilege keys, daily backups with tested restore, and dependency scanning. No system is perfectly secure; if a breach affects you we will notify you and the authority as the law requires.

## 10. Changes

We will publish changes here with a new version and date, and ask you to accept material changes at your next sign-in.
