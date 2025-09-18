#include "TrackingAction.hh"
#include "AirPetTrajectory.hh"
#include "AirPetUserTrackInformation.hh"

#include "G4TrackingManager.hh"
#include "G4Track.hh"

TrackingAction::TrackingAction()
 : G4UserTrackingAction()
{}

TrackingAction::~TrackingAction()
{}

void TrackingAction::PreUserTrackingAction(const G4Track* aTrack)
{
  // Tell the tracking manager to use our custom trajectory class.
  // This is only done once per track.
  fpTrackingManager->SetStoreTrajectory(true);
  fpTrackingManager->SetTrajectory(new AirPetTrajectory(aTrack));

  // Check if this track has custom user information attached.
  // This information (parent momentum) would have been attached by the SteppingAction
  // when this track was created as a secondary.
  G4VUserTrackInformation* userInfo = aTrack->GetUserInformation();
  if (userInfo) {
    auto* customInfo = dynamic_cast<AirPetUserTrackInformation*>(userInfo);
    if (customInfo) {
      auto* traj = static_cast<AirPetTrajectory*>(fpTrackingManager->GimmeTrajectory());
      traj->SetParentMomentum(customInfo->GetParentMomentum());
    }
  }
}

void TrackingAction::PostUserTrackingAction(const G4Track* aTrack)
{
  // This method is called after a track has been fully simulated.
  // We can now retrieve the completed trajectory and fill in the final details.

  auto* traj = static_cast<AirPetTrajectory*>(fpTrackingManager->GimmeTrajectory());

  if (traj) {
    traj->SetFinalTime(aTrack->GetGlobalTime());
    traj->SetFinalMomentum(aTrack->GetMomentum());
    traj->SetFinalPosition(aTrack->GetPosition());
    traj->SetFinalVolume(aTrack->GetVolume()->GetName());
  }
}
