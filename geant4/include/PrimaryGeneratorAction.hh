#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"
#include "globals.hh"

// Forward declarations
class G4GeneralParticleSource;
class G4Event;

/// The PrimaryGeneratorAction class.
///
/// This class uses the G4GeneralParticleSource (GPS) to generate primary
/// particles. The GPS is a powerful tool that allows the user to define

/// the properties of the primary particle(s) using UI commands in a macro
/// file, without needing to recompile the C++ code. This provides maximum
/// flexibility for the virtual-pet application.

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction
{
public:
  PrimaryGeneratorAction();
  virtual ~PrimaryGeneratorAction();

  // This method is called at the beginning of each event.
  virtual void GeneratePrimaries(G4Event* anEvent) override;

private:
  G4GeneralParticleSource* fGPS;
};

#endif