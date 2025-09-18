#ifndef AirPetUserTrackInformation_h
#define AirPetUserTrackInformation_h 1

#include "G4VUserTrackInformation.hh"
#include "G4ThreeVector.hh"
#include "globals.hh"

/// A helper class to attach custom information to a G4Track.
///
/// In this case, we use it to store the momentum of the parent particle
/// at the exact vertex where the current track was created. This is useful
//  for physics analysis, e.g., reconstructing kinematics.

class AirPetUserTrackInformation : public G4VUserTrackInformation
{
public:
  AirPetUserTrackInformation();
  virtual ~AirPetUserTrackInformation();

  // --- Setters and Getters ---
  void SetParentMomentum(G4ThreeVector momentum) { fParentMomentum = momentum; }
  G4ThreeVector GetParentMomentum() const { return fParentMomentum; }

private:
  G4ThreeVector fParentMomentum;
};

#endif
