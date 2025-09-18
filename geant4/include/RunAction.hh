#ifndef RunAction_h
#define RunAction_h 1

#include "G4UserRunAction.hh"
#include "globals.hh"

// Forward declarations
class G4Run;
class EventAction;

/// The RunAction class.
///
/// This class is responsible for actions that happen at the beginning and
/// end of a simulation run. Its primary role here is to manage the creation,
/// writing, and closing of the output n-tuple file using G4AnalysisManager.

class RunAction : public G4UserRunAction
{
public:
  // The constructor takes a pointer to the EventAction.
  // This allows for communication between the two action classes if needed.
  RunAction(EventAction* eventAction);
  virtual ~RunAction();

  // --- G4UserRunAction virtual methods ---
  virtual void BeginOfRunAction(const G4Run*) override;
  virtual void EndOfRunAction(const G4Run*) override;

private:
  EventAction* fEventAction;
};

#endif