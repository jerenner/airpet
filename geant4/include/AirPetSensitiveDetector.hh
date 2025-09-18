#ifndef AirPetSensitiveDetector_h
#define AirPetSensitiveDetector_h 1

#include "G4VSensitiveDetector.hh"
#include "AirPetHit.hh" // Includes the HitsCollection typedef

class G4Step;
class G4HCofThisEvent;

/// A generic sensitive detector for AIRPET.
///
/// It creates instances of AirPetHit for every step with non-zero
/// energy deposition and stores them in the AirPetHitsCollection.

class AirPetSensitiveDetector : public G4VSensitiveDetector
{
public:
  AirPetSensitiveDetector(const G4String& name);
  virtual ~AirPetSensitiveDetector();

  //--- G4VSensitiveDetector virtual methods ---
  virtual void Initialize(G4HCofThisEvent* hce) override;
  virtual G4bool ProcessHits(G4Step* aStep, G4TouchableHistory* ROhist) override;
  virtual void EndOfEvent(G4HCofThisEvent* hce) override;

private:
  AirPetHitsCollection* fHitsCollection;
};

#endif
