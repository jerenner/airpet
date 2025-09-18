#ifndef TrackingAction_h
#define TrackingAction_h 1

#include "G4UserTrackingAction.hh"
#include "globals.hh"

/// User tracking action class.
///
/// Its main purpose is to instantiate our custom AirPetTrajectory object
/// for each track, ensuring that detailed information is stored.

class TrackingAction : public G4UserTrackingAction
{
public:
  TrackingAction();
  virtual ~TrackingAction();

  virtual void PreUserTrackingAction(const G4Track* aTrack) override;
  virtual void PostUserTrackingAction(const G4Track* aTrack) override;
};

#endif
