#include "SteppingAction.hh"
#include "AirPetUserTrackInformation.hh"

#include "G4Step.hh"
#include "G4Track.hh"
#include "G4RunManager.hh"

SteppingAction::SteppingAction()
 : G4UserSteppingAction()
{}

SteppingAction::~SteppingAction()
{}

void SteppingAction::UserSteppingAction(const G4Step* step)
{
  // Get the list of secondary particles created in this step
  const std::vector<const G4Track*>* secondaries = step->GetSecondaryInCurrentStep();

  // Check if any secondaries were produced
  if (secondaries && !secondaries->empty()) {
    // Get the momentum of the parent track (the one that took this step)
    G4ThreeVector parentMomentum = step->GetTrack()->GetMomentum();

    // Loop over all newly created secondary tracks
    for (const auto& secondaryTrack : *secondaries) {
      // Create a new user information object
      auto* userInfo = new AirPetUserTrackInformation();
      userInfo->SetParentMomentum(parentMomentum);

      // Attach this information to the secondary track.
      // This is a mutable operation on a const G4Track*, which is allowed by Geant4.
      const_cast<G4Track*>(secondaryTrack)->SetUserInformation(userInfo);
    }
  }
}
