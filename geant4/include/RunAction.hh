#ifndef RunAction_h
#define RunAction_h 1

#include "G4UserRunAction.hh"
#include "G4UImessenger.hh"
#include "globals.hh"

// Forward declarations
class G4Run;
class G4UIdirectory;
class G4UIcommand;

/// The RunAction class.
///
/// This class is responsible for actions that happen at the beginning and
/// end of a simulation run. Its primary role here is to manage the creation,
/// writing, and closing of the output n-tuple file using G4AnalysisManager.

class RunAction : public G4UserRunAction, public G4UImessenger
{
public:
  // The constructor takes a pointer to the EventAction.
  // This allows for communication between the two action classes if needed.
  RunAction();
  virtual ~RunAction();

  // --- G4UserRunAction virtual methods ---
  virtual void BeginOfRunAction(const G4Run*) override;
  virtual void EndOfRunAction(const G4Run*) override;

  virtual void SetNewValue(G4UIcommand* command, G4String newValue) override;

  G4bool GetSaveParticles() const { return fSaveParticles; }
  G4bool GetSaveHits() const { return fSaveHits; }

private:

  G4UIdirectory* fG4petDir;
  G4UIdirectory* fRunDir;
  G4UIcommand*   fSaveParticlesCmd;
  G4UIcommand*   fSaveHitsCmd;

  G4bool fSaveParticles;
  G4bool fSaveHits;
};

#endif