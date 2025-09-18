#include "ActionInitialization.hh"

// These are the action classes we are about to create in the next steps.
// We include their headers here with the assumption they will exist.
#include "PrimaryGeneratorAction.hh"
#include "RunAction.hh"
#include "EventAction.hh"
#include "SteppingAction.hh"
#include "TrackingAction.hh"


ActionInitialization::ActionInitialization()
 : G4VUserActionInitialization()
{}

ActionInitialization::~ActionInitialization()
{}

void ActionInitialization::BuildForMaster() const
{
  // The master thread manages the overall run. It does not process individual
  // events, so it only needs a RunAction.
  // We pass a new EventAction instance to it to satisfy the constructor.
  auto* eventAction = new EventAction();
  SetUserAction(new RunAction(eventAction));
}

void ActionInitialization::Build() const
{
  // This method is called for each worker thread.
  // Each worker thread gets its own set of action classes.

  // Primary particles are generated here.
  SetUserAction(new PrimaryGeneratorAction());

  // The EventAction is created once per thread.
  auto* eventAction = new EventAction();
  SetUserAction(eventAction);

  // The RunAction is also created per thread and takes the thread-local
  // EventAction pointer. This allows it to access event data.
  SetUserAction(new RunAction(eventAction));

  // SteppingAction is called for every step in the simulation.
  SetUserAction(new SteppingAction());

  // TrackingAction is called at the beginning and end of every track.
  SetUserAction(new TrackingAction());
}