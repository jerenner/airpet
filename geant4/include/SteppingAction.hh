#ifndef SteppingAction_h
#define SteppingAction_h 1

#include "G4UserSteppingAction.hh"
#include "globals.hh"

/// User stepping action class.
///
/// It is invoked at every step of every particle.
/// Here, its main purpose is to catch the creation of secondary particles
/// and attach information about the parent track to them.

class SteppingAction : public G4UserSteppingAction
{
public:
  SteppingAction();
  virtual ~SteppingAction();

  virtual void UserSteppingAction(const G4Step* step) override;
};

#endif
